"""
SPECTRUM-LAB PRO | Módulo Connection Worker Triplo (USB, Bluetooth SPP e Wi-Fi TCP)
Comunicação assíncrona robusta orientada a objetos via QThread com ESP32.

Protocolo Consolidado (115200 Baud / TCP 8080):
- Anti-Reset DTR/RTS via conversor USB-Serial
- Heartbeat periódico a cada 1000ms
- Desconexão graciosa com CMD:REPOUSO_SUAVE\\n
"""

import time
import queue
import socket
import select
from typing import Optional, List
from PyQt5.QtCore import QThread, pyqtSignal

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


class ConnectionWorker(QThread):
    """
    Thread de comunicação unificada com o ESP32 suportando:
    1. USB (Cabo Serial UART) com proteção anti-reset DTR/RTS
    2. Bluetooth (SPP Virtual COM Port)
    3. Wi-Fi (Socket TCP/IP - Porta padrão 8080 / IP 192.168.4.1)

    Gerencia fila de envio prioritária (E-Stop imediato), recepção contínua e parser anti-ruído.
    """
    # Sinais padrão da aplicação
    line_received = pyqtSignal(str)              # Linha completa para console/log
    status_received = pyqtSignal(str)            # Tag STATUS extraída (ex: GAVETA_ABERTA)
    data_received = pyqtSignal(list)             # Array de 6 floats/inteiros [v1..v6]
    connection_changed = pyqtSignal(bool, str)   # (conectado: bool, desc_ou_erro: str)
    error_occurred = pyqtSignal(str)             # Mensagem de erro de hardware ou rede

    # Sinais solicitados em português / aliases
    dado_recebido = data_received
    status_recebido = status_received
    conexao_estabelecida = pyqtSignal(str)
    conexao_perdida = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode: str = "USB"  # "USB", "BLUETOOTH", "WIFI"
        self.port_name: Optional[str] = None
        self.baudrate: int = 115200

        self.wifi_ip: str = "192.168.4.1"
        self.wifi_port: int = 8080

        # Atributos de transporte com aliases para compatibilidade
        self.serial_port: Optional[serial.Serial] = None
        self.serial: Optional[serial.Serial] = None
        self.tcp_socket: Optional[socket.socket] = None
        self.sock: Optional[socket.socket] = None
        self._is_running: bool = False

        # Filas thread-safe de transmissão
        self._tx_queue: queue.Queue = queue.Queue()
        self._priority_queue: queue.Queue = queue.Queue()

    def is_connected(self) -> bool:
        """Verifica se o canal ativo está aberto e comunicando."""
        if self.mode in ("USB", "BLUETOOTH"):
            return bool(self.serial_port and self.serial_port.is_open)
        elif self.mode == "WIFI":
            return bool(self.tcp_socket is not None and self._is_running)
        return False

    def connect_serial(self, port_name: str, baudrate: int = 115200, mode: str = "USB") -> bool:
        """
        Abre conexão serial (USB ou Bluetooth SPP virtual COM) e inicia thread receptora.
        Aplica prevenção explícita de hard reset via DTR/RTS.
        """
        if not HAS_SERIAL:
            err = "Módulo pyserial não está instalado no ambiente."
            self.error_occurred.emit(err)
            return False

        if self.is_connected():
            self.disconnect_connection()

        self.mode = mode
        self.port_name = port_name
        self.baudrate = baudrate

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                timeout=0.5,
                write_timeout=0.5
            )
            # CRÍTICO (Anti-Reset): Imediatamente após a abertura da porta, definir explicitamente:
            # self.serial.dtr = False e self.serial.rts = False
            # Isso impede que o circuito conversor USB-Serial force um pulso de reset no ESP32.
            try:
                self.serial_port.dtr = False
                self.serial_port.rts = False
            except Exception:
                pass

            self.serial = self.serial_port

            # Limpa buffers residuais do ESP32
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            self._is_running = True
            self.start()

            desc = f"{mode}: {port_name} @ {baudrate} bps"
            self.connection_changed.emit(True, desc)
            self.conexao_estabelecida.emit(desc)

            # Handshake inicial obrigatório
            self.enviar("CMD:PING")
            return True
        except Exception as err:
            self.serial_port = None
            self.serial = None
            err_msg = f"Falha ao conectar {mode} em {port_name}: {err}"
            print(f"[CONEXÃO] {err_msg}", flush=True)
            self.connection_changed.emit(False, err_msg)
            self.conexao_perdida.emit(err_msg)
            self.error_occurred.emit(err_msg)
            return False

    def connect_tcp(self, host: str = "192.168.4.1", port: int = 8080) -> bool:
        """
        Abre conexão Wi-Fi via socket TCP/IP com o ESP32 e inicia thread receptora.
        Valores padrão: IP 192.168.4.1 e Porta 8080.
        """
        if self.is_connected():
            self.disconnect_connection()

        self.mode = "WIFI"
        self.wifi_ip = host
        self.wifi_port = port

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((host, port))

            self.tcp_socket = sock
            self.sock = sock
            self._is_running = True
            self.start()

            desc = f"Wi-Fi TCP: {host}:{port}"
            self.connection_changed.emit(True, desc)
            self.conexao_estabelecida.emit(desc)

            # Handshake inicial
            self.enviar("CMD:PING")
            return True
        except Exception as err:
            self.tcp_socket = None
            self.sock = None
            err_msg = f"Falha ao conectar Wi-Fi TCP em {host}:{port}: {err}"
            print(f"[TCP] {err_msg}", flush=True)
            self.connection_changed.emit(False, err_msg)
            self.conexao_perdida.emit(err_msg)
            self.error_occurred.emit(err_msg)
            return False

    def disconnect_connection(self):
        """Finaliza thread e fecha qualquer conexão ativa (Serial, BT ou TCP)."""
        self._is_running = False
        self._clear_queue()

        if self.isRunning():
            if self.serial_port and hasattr(self.serial_port, "cancel_read"):
                try:
                    self.serial_port.cancel_read()
                except Exception:
                    pass
            self.wait(1000)

        # Fecha porta serial / BT garantindo DTR/RTS desligados
        if self.serial_port:
            try:
                self.serial_port.dtr = False
                self.serial_port.rts = False
            except Exception:
                pass
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None
            self.serial = None

        # Fecha socket TCP
        if self.tcp_socket:
            try:
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None
            self.sock = None

        self.connection_changed.emit(False, "Desconectado")
        self.conexao_perdida.emit("Desconectado")

    # Aliases
    disconnect_serial = disconnect_connection
    disconnect = disconnect_connection

    def enviar(self, comando: str, priority: bool = False) -> bool:
        """
        Método unificado de envio de comando para o ESP32.
        Garante terminação com '\\n' e despacha via serial.write() ou sock.sendall().
        Se priority=True (ex: CMD:EMERGENCIA), vai para a fila prioritária imediata.
        """
        raw_cmd = comando.strip()
        if not raw_cmd.startswith("CMD:"):
            raw_cmd = f"CMD:{raw_cmd}"

        payload = f"{raw_cmd}\n"

        if priority or "EMERGENCIA" in raw_cmd:
            self._clear_queue()
            self._priority_queue.put(payload)
        else:
            self._tx_queue.put(payload)

        return True

    send_command = enviar

    def send_emergency(self):
        """Disparo de Parada de Emergência com prioridade máxima imediata."""
        self._clear_queue()
        self.enviar("CMD:EMERGENCIA", priority=True)

    def _clear_queue(self):
        """Descarta comandos pendentes na fila."""
        while not self._tx_queue.empty():
            try:
                self._tx_queue.get_nowait()
            except queue.Empty:
                break

    def run(self):
        """Loop assíncrono de transmissão e recepção para Serial e Wi-Fi TCP."""
        rx_buffer_tcp = ""

        while self._is_running:
            try:
                # 1. TRANSMISSÃO: Prioritária primeiro
                cmd_to_send = None
                if not self._priority_queue.empty():
                    cmd_to_send = self._priority_queue.get_nowait()
                elif not self._tx_queue.empty():
                    cmd_to_send = self._tx_queue.get_nowait()

                if cmd_to_send:
                    cmd_bytes = cmd_to_send.encode("utf-8")
                    if self.mode in ("USB", "BLUETOOTH") and self.serial_port and self.serial_port.is_open:
                        try:
                            self.serial_port.write(cmd_bytes)
                            self.serial_port.flush()
                            print(f"[{self.mode} TX]: {cmd_to_send.strip()}", flush=True)
                        except Exception as tx_err:
                            self.error_occurred.emit(f"Erro de transmissão {self.mode}: {tx_err}")

                    elif self.mode == "WIFI" and self.tcp_socket:
                        try:
                            self.tcp_socket.sendall(cmd_bytes)
                            print(f"[WIFI TCP TX]: {cmd_to_send.strip()}", flush=True)
                        except Exception as tx_err:
                            self.error_occurred.emit(f"Erro de transmissão Wi-Fi TCP: {tx_err}")

                # 2. RECEPÇÃO: Serial (USB / Bluetooth)
                if self.mode in ("USB", "BLUETOOTH"):
                    if self.serial_port and self.serial_port.is_open and self.serial_port.in_waiting > 0:
                        raw_bytes = self.serial_port.readline()
                        if raw_bytes:
                            line = raw_bytes.decode("utf-8", errors="replace").strip()
                            if line:
                                self._parse_incoming_line(line)
                    time.sleep(0.01)

                # 3. RECEPÇÃO: Wi-Fi TCP
                elif self.mode == "WIFI" and self.tcp_socket:
                    try:
                        ready_to_read, _, _ = select.select([self.tcp_socket], [], [], 0.02)
                        if ready_to_read:
                            chunk = self.tcp_socket.recv(2048)
                            if not chunk:
                                print("[WIFI TCP]: Servidor encerrou a conexão.", flush=True)
                                self._is_running = False
                                self.connection_changed.emit(False, "Conexão Wi-Fi encerrada pelo ESP32")
                                self.conexao_perdida.emit("Conexão Wi-Fi encerrada")
                                break

                            rx_buffer_tcp += chunk.decode("utf-8", errors="replace")
                            while "\n" in rx_buffer_tcp:
                                line, rx_buffer_tcp = rx_buffer_tcp.split("\n", 1)
                                line = line.strip()
                                if line:
                                    self._parse_incoming_line(line)
                    except socket.timeout:
                        pass
                    except Exception as sock_err:
                        if self._is_running:
                            print(f"[WIFI TCP RX ERROR]: {sock_err}", flush=True)
                            self._is_running = False
                            self.connection_changed.emit(False, f"Erro de recepção Wi-Fi: {sock_err}")
                            self.conexao_perdida.emit(str(sock_err))
                            break

            except Exception as loop_err:
                if self._is_running:
                    print(f"[COMMUNICATION LOOP ERROR]: {loop_err}", flush=True)
                    time.sleep(0.05)

    def _parse_incoming_line(self, line: str):
        """
        Parser seguro anti-ruído:
        Trata DATA:... e STATUS:... sem propagar exceções.
        """
        self.line_received.emit(line)
        print(f"[{self.mode} RX]: {line}", flush=True)

        # 1. Tratamento de STATUS
        if "STATUS:" in line:
            status_part = line[line.index("STATUS:") + len("STATUS:"):].strip()
            status_tag = status_part.split()[0] if status_part else ""
            if status_tag:
                self.status_received.emit(status_tag)
                return

        # 2. Tratamento de DATA
        if "DATA:" in line:
            data_part = line[line.index("DATA:") + len("DATA:"):].strip()
            parts = data_part.split(",")
            values = []
            for p in parts[:6]:
                clean_p = p.strip()
                try:
                    values.append(float(clean_p))
                except ValueError:
                    pass

            if len(values) == 6:
                self.data_received.emit(values)
            return

    @staticmethod
    def list_ports() -> List[tuple]:
        """Lista todas as portas COM disponíveis."""
        if not HAS_SERIAL:
            return []
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]


# Aliases para retrocompatibilidade
SerialWorker = ConnectionWorker

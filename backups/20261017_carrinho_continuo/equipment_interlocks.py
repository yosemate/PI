"""Sequenciamento confirmado da porta e autorização temporária da carcaça."""
import os
import time

from PyQt5.QtWidgets import QDialog
from auth_dialogs import DialogLogin


class EquipmentInterlocks:
    EXPECTED = {
        "CMD:ABRIR_PORTA": "PORTA_ABERTA", "CMD:FECHAR_PORTA": "PORTA_FECHADA",
        "CMD:ABRIR_GAVETA": "GAVETA_ABERTA", "CMD:FECHAR_GAVETA": "GAVETA_FECHADA",
        "CMD:AVANCAR_SENSOR": "SENSOR_AVANCADO", "CMD:RECUAR_SENSOR": "SENSOR_RECUADO",
    }
    COMMANDS = {
        "CMD:ABRIR_PORTA", "CMD:FECHAR_PORTA", "CMD:ABRIR_GAVETA",
        "CMD:FECHAR_GAVETA", "CMD:AVANCAR_SENSOR", "CMD:RECUAR_SENSOR",
        "CMD:LER_ESPECTRO", "CMD:LER_ESCURO",
    }

    def __init__(self, window):
        self.window = window
        self.reset()

    def reset(self):
        self.capable = False
        self.manual_capable = False
        self.manual_motion = False
        self.open = self.closed = self.housing_closed = None
        self.drawer_closed = False  # Confirmação de comando; não há chave na gaveta.
        self.sample_confirmed = False
        self.authorized = False
        self.pending = None
        self.authenticating = False
        self.received_at = 0
        self.expected_motion = None

    def revoke(self, notify=True):
        had_access = self.authorized
        self.authorized = False
        if had_access and notify and self.window.is_serial_connected():
            self.window.serial_worker.send_command("CMD:REVOGAR_CARCACA")

    def cancel(self):
        self.pending = None
        self.expected_motion = None
        self.manual_motion = False
        self.sample_confirmed = False
        self.drawer_closed = False
        self.revoke()

    def update(self, line):
        if not line.startswith("PORTA:"):
            return False
        try:
            values = dict(part.split(":", 1) for part in line[6:].split("|"))
            if not all(values[key] in ("0", "1") for key in ("ABERTA", "FECHADA", "CARCACA_FECHADA")):
                raise ValueError("Estado de fim de curso inválido")
        except (ValueError, KeyError):
            self.window._fail_operation("Telemetria dos fins de curso inválida.")
            return True
        previous = self.housing_closed
        self.open = values["ABERTA"] == "1"
        self.closed = values["FECHADA"] == "1"
        self.housing_closed = values["CARCACA_FECHADA"] == "1"
        self.received_at = time.monotonic()
        if self.housing_closed:
            self.revoke()
        if previous is True and not self.housing_closed:
            self.revoke()
            if self.busy():
                self.window._fail_operation("Carcaça aberta durante a operação. Autentique novamente para continuar.")
        if self.open and self.closed:
            self.window._fail_operation("Os dois fins de curso da porta estão ativos simultaneamente.")
        elif (self.window._batch or (self.expected_motion == "SENSOR_AVANCADO" and not self.manual_motion)
              or self.window.fsm_state == "REP_AGUARDANDO_PROXIMA") and (not self.closed or self.open):
            self.window._fail_operation("Porta deixou de estar fechada durante avanço ou aquisição.")
        elif not self.manual_motion and self.expected_motion in ("GAVETA_ABERTA", "GAVETA_FECHADA") and (not self.open or self.closed):
            self.window._fail_operation("Porta deixou de estar aberta durante movimento da gaveta.")
        self.refresh_indicator()
        self.window._refresh_controls()
        return True

    def busy(self):
        w = self.window
        return bool(self.pending or w.fsm_state != "IDLE" or w._manual_pending or w._batch)

    def refresh_indicator(self):
        w = self.window
        label = getattr(w, "lbl_housing_state", None)
        if label is not None:
            if self.housing_closed is None:
                text, color = "Carcaça: sem confirmação", "#94A3B8"
            elif self.housing_closed:
                text, color = "Carcaça fechada • chave ativa", "#10B981"
            elif self.authorized:
                text, color = "Carcaça aberta • acesso autorizado", "#F59E0B"
            else:
                text, color = "Carcaça aberta • exige autenticação", "#EF4444"
            label.setText(text)
            label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 6px;")
        door = getattr(w, "lbl_door_state", None)
        if door is not None:
            state = "sem confirmação" if self.open is None else (
                "falha nas chaves" if self.open and self.closed else
                "aberta" if self.open else "fechada" if self.closed else "entre posições")
            door.setText("Porta: " + state)
        if w._manual_dialog:
            w._manual_dialog.update_interlocks_and_leds()

    def authenticate(self):
        w = self.window
        if self.authenticating:
            return False
        epoch = w._operation_epoch
        self.authenticating = True
        try:
            dlg = DialogLogin(w.auth_manager, w._manual_dialog or w)
            dlg.setWindowTitle("Carcaça aberta — autorizar esta operação")
            accepted = dlg.exec_() == QDialog.Accepted
            user = dlg.usuario_logado if accepted else None
        finally:
            self.authenticating = False
        if not user or epoch != w._operation_epoch or not w.is_serial_connected():
            return False
        w.current_operator_name = user.get("username", "Operador")
        w.log_message("[CARCAÇA] Operação com carcaça aberta autorizada por " + w.current_operator_name)
        return True

    def confirm_sample(self):
        w = self.window
        epoch = w._operation_epoch
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            accepted = getattr(w, "_auto_confirm_dialog", False)
        else:
            dlg = w._create_placement_confirmation()
            accepted = dlg.exec_() == QDialog.Accepted
        return accepted and epoch == w._operation_epoch and w.is_serial_connected()

    def wait_for(self, command, expected, continuation):
        w = self.window
        self.pending = (expected, continuation, w._operation_epoch)
        self.expected_motion = expected
        w.lbl_cycle_status.setText("Status: aguardando " + {
            "PORTA_ABERTA": "fim de curso da porta aberta",
            "PORTA_FECHADA": "fim de curso da porta fechada",
            "CARCACA_AUTORIZADA": "autorização do ESP32",
        }.get(expected, expected))
        if not w.serial_worker.send_command(command):
            w._fail_operation("Não foi possível enviar o comando de intertravamento.", send_stop=False)
            return False
        if expected in ("PORTA_ABERTA", "PORTA_FECHADA"):
            w._hardware_watchdog.stop()
            for _, timer in w._manual_pending.values():
                timer.stop()
        else:
            w._hardware_watchdog.start(4000)
        w._refresh_controls()
        return True

    def prepare(self, command, manual=False):
        """None libera envio; bool indica comando adiado ou rejeitado."""
        if command not in self.COMMANDS:
            return None
        w = self.window
        if manual and command in self.EXPECTED and not self.manual_capable:
            w._cancel_equipment_request("Atualize o firmware para liberar os comandos manuais independentes.")
            return False
        if not self.capable or self.housing_closed is None or time.monotonic() - self.received_at > 6:
            w._fail_operation("Atualize o firmware e aguarde a confirmação dos fins de curso.")
            return False
        if self.pending:
            return False
        if not self.housing_closed and not self.authorized:
            # Nenhum movimento é enviado antes do login e do ACK do firmware.
            w._hardware_watchdog.stop()
            for _, timer in w._manual_pending.values():
                timer.stop()
            if not self.authenticate():
                w._cancel_equipment_request("Operação cancelada: carcaça aberta sem autorização.")
                return False
            return self.wait_for("CMD:AUTORIZAR_CARCACA", "CARCACA_AUTORIZADA",
                                 lambda: w.send_serial_command(command, manual=manual))
        if manual and command in self.EXPECTED:
            if command in ("CMD:ABRIR_GAVETA", "CMD:FECHAR_GAVETA"):
                self.drawer_closed = False
                self.sample_confirmed = False
            return None
        if command == "CMD:ABRIR_GAVETA":
            if not self.open or self.closed:
                return self.wait_for("CMD:ABRIR_PORTA", "PORTA_ABERTA",
                                     lambda: w.send_serial_command(command))
            self.drawer_closed = False
            self.sample_confirmed = False
        elif command == "CMD:FECHAR_GAVETA":
            if not self.open or self.closed:
                return self.wait_for("CMD:ABRIR_PORTA", "PORTA_ABERTA",
                                     lambda: w.send_serial_command(command))
            if not self.sample_confirmed and not self.confirm_sample():
                w._cancel_equipment_request("Fechamento cancelado. Gaveta permanece aberta.")
                return False
            self.sample_confirmed = False
            self.drawer_closed = False
        elif command == "CMD:AVANCAR_SENSOR":
            if not self.drawer_closed:
                w._fail_operation("Avanço bloqueado: fechamento da gaveta ainda não confirmado.")
                return False
            if not self.closed or self.open:
                return self.wait_for("CMD:FECHAR_PORTA", "PORTA_FECHADA",
                                     lambda: w.send_serial_command(command))
        elif command in ("CMD:LER_ESPECTRO", "CMD:LER_ESCURO"):
            if not self.drawer_closed or not self.closed or self.open:
                w._fail_operation("Leitura bloqueada: gaveta e porta precisam estar fechadas.")
                return False
        elif command == "CMD:FECHAR_PORTA" and not self.drawer_closed:
            w._cancel_equipment_request("Feche e confirme a gaveta antes de fechar a porta.")
            return False
        return None

    def on_status(self, status, verified=False):
        w = self.window
        was_manual = False
        if status in self.EXPECTED.values() and not verified:
            if status != self.expected_motion:
                w.log_message("[INTERTRAVAMENTO] Confirmação mecânica inesperada descartada: " + status)
                return True
            self.expected_motion = None
            was_manual = self.manual_motion
            self.manual_motion = False
        if status == "MANUAL_PROTOCOLO_1":
            self.manual_capable = True
            w._refresh_controls()
            return True
        if status == "PORTA_PROTOCOLO_1":
            self.capable = True
            w._refresh_controls()
            return True
        if status.startswith("CARCACA_AUTORIZACAO_REVOGADA"):
            active = self.authorized and self.busy() and not status.endswith(":CARCACA_FECHADA")
            self.revoke(notify=False)
            self.refresh_indicator()
            if active:
                w._fail_operation("Autorização para carcaça aberta encerrada pelo ESP32.")
            return True
        if status in ("CARCACA_ABERTA", "CARCACA_FECHADA"):
            w.serial_worker.send_command("CMD:ESTADO_PORTA")
            return True
        if status == "PORTA_ABERTA" and (not self.open or self.closed):
            w._fail_operation("Porta aberta sem confirmação válida do fim de curso.")
            return True
        if status == "PORTA_FECHADA" and (not self.closed or self.open):
            w._fail_operation("Porta fechada sem confirmação válida do fim de curso.")
            return True
        if status in ("ABRINDO_GAVETA", "FECHANDO_GAVETA"):
            self.drawer_closed = False
        if status == "GAVETA_ABERTA":
            self.drawer_closed = False
            self.sample_confirmed = False
        if self.pending and status == self.pending[0]:
            expected, callback, epoch = self.pending
            if expected == "PORTA_ABERTA" and (not self.open or self.closed):
                w._fail_operation("Porta aberta sem confirmação válida do fim de curso.")
                return True
            if expected == "PORTA_FECHADA" and (not self.closed or self.open):
                w._fail_operation("Porta fechada sem confirmação válida do fim de curso.")
                return True
            self.pending = None
            w._hardware_watchdog.stop()
            if epoch != w._operation_epoch:
                return True
            if expected == "CARCACA_AUTORIZADA":
                self.authorized = not self.housing_closed
                self.refresh_indicator()
                for _, timer in w._manual_pending.values():
                    timer.start(30000)
            callback()
            return True
        if status == "GAVETA_FECHADA":
            self.drawer_closed = True
            if not was_manual and (not self.closed or self.open):
                # A FSM só recebe a confirmação de gaveta após a porta fechar.
                self.wait_for("CMD:FECHAR_PORTA", "PORTA_FECHADA",
                              lambda: w._on_serial_status_received("GAVETA_FECHADA", _verified=True))
                return True
        return False

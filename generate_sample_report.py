"""Generate a clearly labeled sample report; all values are simulated."""
from pathlib import Path
from pdf_generator import generate_pdf_report


def main():
    output = Path(__file__).resolve().parent / 'output/pdf/laudo_modelo_modernizado.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    response = [38.4, 52.1, 64.7, 61.2, 70.8, 76.5]
    adc = [30 + value / 100 * 4970 for value in response]
    scans = [[value + delta for value in adc] for delta in (-3, -1, 0, 1, 3)]
    snapshot = {
        'is_calibrated': True, 'calibration_id': 'DEMO-20261009-REFERENCIA-001',
        'reference_label': 'Cartão branco fosco - exemplo simulado',
        'timestamp': '2026-10-09 09:00:00', 'operador': 'Operador de demonstração',
        'dark_method': 'led_off', 'vetor_branco': [5000]*6, 'vetor_escuro': [30]*6,
        'settings': {'sensor': 'AS7263', 'gain': 64.0, 'integration_ms': 140.0, 'led_ma': 50.0},
        'white_stats': {'n': 10, 'cv_percent': [.21, .18, .24, .20, .17, .23]},
        'dark_stats': {'n': 10, 'stdevs': [.9, 1.1, .8, 1.2, .9, 1.0]},
        'notes': 'DADOS SIMULADOS para avaliação do modelo visual; não correspondem a um ensaio real.'}
    generate_pdf_report(output, sample_id='DEMO-POLPA-2026', operator='Operador de demonstração',
                        kappa_value=16.85, kappa_status='Estimativa demonstrativa - dados simulados',
                        values=response, raw_adc_values=adc, ratio_celulose=response[1]/response[2],
                        ratio_agua=response[5]/response[3], calibration_snapshot=snapshot,
                        acquisition_count=5, raw_scans=scans, timestamp='09/10/2026 09:15:00', com_port='USB / COM3')
    print(output)


if __name__ == '__main__':
    main()

import os
import time
import datetime
from datetime import datetime as dt
import logging
import threading
from src import config, api, utils


def process_file_logic(file_path: str, base_url: str, tz_offset: int, target_eps: int,
                       stop_event: threading.Event, start_index: int = 1):
    access_token = os.path.splitext(os.path.basename(file_path))[0]
    target_url = f"{base_url}/api/v1/{access_token}/telemetry"
    http_session = api.get_requests_session()

    min_cycle_time = 1.0 / target_eps if target_eps > 0 else 0
    logging.info(f"[{access_token}] Retomando linha {start_index}. Meta: {target_eps} EPS constantes.")

    for header, chunk in utils.file_line_generator(file_path, start_idx=start_index):
        if stop_event.is_set():
            break

        for current_idx, line in chunk:
            if stop_event.is_set():
                break

            cycle_start = time.time()
            fields = line.split(',')

            if len(fields) == 14:
                try:
                    timestring = f'{fields[0]}+00:00'
                    dtime = dt.strptime(timestring, '%d/%m/%Y %H:%M:%S%z') + datetime.timedelta(hours=(-1) * tz_offset)

                    values = {
                        's1d1': utils.str_to_float_or_nan(fields[1]), 's1d2': utils.str_to_float_or_nan(fields[2]),
                        's2d1': utils.str_to_float_or_nan(fields[3]), 's2d2': utils.str_to_float_or_nan(fields[4]),
                        's3d1': utils.str_to_float_or_nan(fields[5]), 's3d2': utils.str_to_float_or_nan(fields[6]),
                        's4d1': utils.str_to_float_or_nan(fields[7]), 's4d2': utils.str_to_float_or_nan(fields[8]),
                        'vbat': float(fields[9]), 'lbat': fields[10].strip() == 'True',
                        'rssi': float(fields[11]), 'snr': float(fields[12])
                    }
                    payload = {"ts": int(dtime.timestamp()) * 1000, "values": utils.clean_values(values)}

                    r = http_session.post(target_url, json=payload, timeout=10)
                    if r.status_code == 200:
                        with config.state_lock:
                            config.state["success_count"] += 1
                    else:
                        utils.write_to_dlq(file_path, header, line, f"HTTP_{r.status_code}")
                        with config.state_lock:
                            config.state["error_count"] += 1
                except Exception as e:
                    utils.write_to_dlq(file_path, header, line, "REDE_ERRO")
                    with config.state_lock:
                        config.state["error_count"] += 1
            else:
                utils.write_to_dlq(file_path, header, line, "COLUNAS_INVALIDAS")
                with config.state_lock:
                    config.state["error_count"] += 1

            with config.state_lock:
                config.state["processed_count"] += 1

            if current_idx % 1000 == 0:
                utils.manage_checkpoint(file_path, current_idx)

            elapsed = time.time() - cycle_start
            if elapsed < min_cycle_time:
                time.sleep(min_cycle_time - elapsed)

    if not stop_event.is_set():
        utils.manage_checkpoint(file_path, clear=True)


def orchestrate_queue(files_to_process: list, base_url: str, tz_offset: int, target_eps: int,
                      completion_callback, stop_event: threading.Event):
    files_processed = []
    try:
        logging.info(f'--- Iniciando Ingestão Cadenciada ({target_eps} EPS) ---')
        for file_path in files_to_process:
            if stop_event.is_set(): break
            start_idx = utils.get_checkpoint(file_path)
            files_processed.append(file_path)
            process_file_logic(file_path, base_url, tz_offset, target_eps, stop_event, start_index=start_idx)

        if not stop_event.is_set() and files_processed:
            report_name = utils.generate_audit_report(files_processed)
            logging.info(f'Relatório gerado: {report_name}')

    except Exception as e:
        logging.fatal(f'Falha na orquestração: {str(e)}')
    finally:
        config.state["is_running"] = False
        completion_callback(files_processed)
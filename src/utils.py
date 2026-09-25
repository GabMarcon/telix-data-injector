import os
import json
import math
import time
import datetime
from datetime import datetime as dt
from src import config


def str_to_float_or_nan(in_str: str) -> float:
    return float('nan') if in_str.strip() == '' else float(in_str)


def clean_values(values_dict: dict) -> dict:
    return {k: v for k, v in values_dict.items() if not (isinstance(v, float) and math.isnan(v))}


def file_line_generator(filepath, start_idx=1, chunk_size=2000):
    """Leitura em Streaming (Lazy Loading) para arquivos massivos."""
    with open(filepath, 'r', encoding='utf-8') as f:
        header = f.readline()
        for _ in range(1, start_idx):
            f.readline()

        chunk = []
        current_idx = start_idx
        for line in f:
            chunk.append((current_idx, line))
            current_idx += 1
            if len(chunk) >= chunk_size:
                yield header, chunk
                chunk = []
        if chunk:
            yield header, chunk


def manage_checkpoint(filepath: str, last_line_idx: int = None, clear: bool = False):
    checkpoints = {}
    if os.path.exists(config.CHECKPOINT_FILE):
        try:
            with open(config.CHECKPOINT_FILE, 'r') as f:
                checkpoints = json.load(f)
        except Exception:
            pass

    abs_path = os.path.abspath(filepath)
    if clear:
        checkpoints.pop(abs_path, None)
    elif last_line_idx is not None:
        checkpoints[abs_path] = last_line_idx

    with open(config.CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoints, f)


def get_checkpoint(filepath: str) -> int:
    try:
        with open(config.CHECKPOINT_FILE, 'r') as f:
            return json.load(f).get(os.path.abspath(filepath), 1)
    except Exception:
        return 1


def write_to_dlq(original_filepath: str, header: str, raw_line: str, error_msg: str):
    """Isola falhas no Dead-Letter Queue."""
    base_name = os.path.splitext(os.path.basename(original_filepath))[0]
    dlq_file = os.path.join(os.path.dirname(original_filepath), f"{base_name}_FALHAS.csv")

    with config.dlq_lock:
        exists = os.path.exists(dlq_file)
        with open(dlq_file, 'a', encoding='utf-8') as f:
            if not exists and header:
                f.write(header.strip() + ",MOTIVO_ERRO\n")
            f.write(raw_line.strip() + f",{error_msg}\n")


def generate_audit_report(files_processed: list) -> str:
    """Gera comprovante de auditoria da execução."""
    report_name = f"Relatorio_Reinsercao_{dt.now().strftime('%Y%m%d_%H%M%S')}.txt"
    elapsed = time.time() - config.state["start_time"]

    with open(report_name, 'w', encoding='utf-8') as f:
        f.write("=" * 40 + "\nRELATÓRIO DE REINSERÇÃO TELIX\n" + "=" * 40 + "\n\n")
        f.write(f"Data de Execução: {dt.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write(f"Tempo Total: {str(datetime.timedelta(seconds=int(elapsed)))}\n")
        f.write(f"Linhas Processadas: {config.state['processed_count']}\n")
        f.write(f"Sucessos (Telix OK): {config.state['success_count']}\n")
        f.write(f"Falhas (DLQ): {config.state['error_count']}\n\n")
        f.write("Arquivos:\n")
        for file in files_processed:
            f.write(f" - {os.path.basename(file)}\n")
        f.write("\n" + "=" * 40 + "\n")
    return report_name


def scan_targets_async(paths, is_folder, callback):
    """Executa varredura (Dry-Run) em segundo plano."""
    total_lines = 0
    invalid_lines = 0
    files = [os.path.join(paths[0], f) for f in os.listdir(paths[0]) if
             f.endswith(('.csv', '.txt'))] if is_folder else paths

    try:
        for file in files:
            with open(file, 'r', encoding='utf-8') as f:
                header = f.readline()
                for line in f:
                    total_lines += 1
                    if len(line.split(',')) != 14:
                        invalid_lines += 1
        callback(files, total_lines, invalid_lines, "OK")
    except Exception as e:
        callback([], 0, 0, f"Erro: {str(e)}")
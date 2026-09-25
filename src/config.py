import threading

# Constantes de Arquivos
CONFIG_FILE = "andro2telix_config.json"
CHECKPOINT_FILE = ".telix_checkpoints.json"

# Estado Global da Aplicação
state = {
    "is_running": False,
    "start_time": 0,
    "processed_count": 0,
    "success_count": 0,
    "error_count": 0,
    "total_target": 0
}

# Locks de Concorrência para Multithreading
state_lock = threading.Lock()
dlq_lock = threading.Lock()
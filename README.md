# Telix Data Injector

Aplicação de ETL (Extract, Transform, Load) desenvolvida para reinserção de telemetria massiva na plataforma Telix. Projetada para alta performance, tolerância a falhas e controle de vazão de rede, garantindo que grandes volumes de dados de dataloggers sejam integrados sem sobrecarregar a Cadeia de Regras (Rule Engine) do servidor.

## Principais Funcionalidades

*   **Paced Ingestion (Controlo de EPS):** Limita a taxa de requisições por segundo para evitar sobrecarga e Timeouts no processamento do ThingsBoard.
*   **Dead-Letter Queue (DLQ):** Isola automaticamente linhas com erro de rede ou formatação incorreta em ficheiros `_FALHAS.csv`, garantindo perda zero de dados e facilitando a auditoria.
*   **Checkpointing Seguro:** Guarda o estado do processamento continuamente. Em caso de falha de energia ou aborto manual, o sistema retoma exatamente da linha onde parou.
*   **Streaming de Dados (Lazy Loading):** Lê os ficheiros em pequenos blocos sob demanda, permitindo o processamento de ficheiros de dezenas de gigabytes com uso mínimo de memória RAM.
*   **Circuit Breaker (Anti-DDoS):** Congela preventivamente o envio caso o servidor retorne erros de saturação (HTTP 429 ou 503).
*   **Auditoria Automática:** Gera relatórios `.txt` no final de cada lote processado.

---

## Estrutura do Projeto

O código fonte segue o princípio de Responsabilidade Única (SOLID) para facilitar a manutenção e escalabilidade.

```text
telix-data-injector/
├── requirements.txt
├── main.py             # Ponto de entrada da aplicação
└── src/
    ├── __init__.py
    ├── config.py       # Estado global, constantes e Locks de concorrência
    ├── utils.py        # DLQ, Checkpointing, Parsing e relatórios
    ├── api.py          # Gestão de sessões HTTP e política de Retries
    ├── engine.py       # Lógica de telemetria e ingestão cadenciada
    └── gui.py          # Interface CustomTkinter e ToolTips
```

---

## Instalação e Configuração

**Pré-requisitos:** Python 3.8 ou superior instalado.

1.  Clone este repositório para a máquina local.
2.  Abra o terminal na pasta do projeto e instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```
3.  Execute o sistema:
    ```bash
    python main.py
    ```

---

## Como Utilizar

1.  **Configuração de Destino:** Selecione se o ambiente alvo é a Nuvem (https) ou um Servidor Interno (http + porta).
2.  **Fuso Horário (Offset):** Ajuste a diferença de horas. Se os dados do equipamento estiverem em UTC, utilize `-3` para converter para o horário local.
3.  **Limite de Leituras (EPS):** Defina a velocidade máxima de inserção. **Recomendado: 25 a 50**. Valores acima de 100 podem enfileirar mensagens indefinidamente na Rule Engine do servidor.
4.  **Seleção de Dados:** 
    *   Clique em **Selecionar CSV** para um ficheiro único, ou **Selecionar Pasta** para processamento em lote.
    *   O sistema fará uma validação prévia de integridade. Se houver um envio inacabado anterior, o sistema perguntará se deseja retomar pelo *Checkpoint*.
5.  **Monitoramento:** Clique em **Iniciar Operação**. O HUD exibirá o tempo estimado (ETA) e os registos em tempo real.

---

## Estrutura do Ficheiro de Origem

O sistema exige rigorosamente **14 colunas** separadas por vírgula (`,`). A primeira linha é sempre assumida como cabeçalho e ignorada.

| Coluna | Nome Esperado | Tipo de Dado | Observação |
| :--- | :--- | :--- | :--- |
| 1 | Data/Hora | String (Data) | Formato obrigatório: `DD/MM/YYYY HH:MM:SS` |
| 2 a 9 | S1D1 a S4D2 | Decimal (Float) | Leituras dos sensores. Células vazias tornam-se `NaN`. |
| 10 | VBat | Decimal (Float) | Tensão da bateria. |
| 11 | LBat | Booleano | Bateria fraca (`True` ou `False`). |
| 12 | RSSI | Decimal (Float) | Nível de sinal. |
| 13 | SNR | Decimal (Float) | Relação sinal-ruído. |
| 14 | Extra | String | Geralmente vazio, mas a vírgula separadora deve existir. |

---

## Resolução de Problemas Comuns

*   **A velocidade travou em 0 reg/s:** O *Circuit Breaker* pode ter sido ativado por lentidão no servidor, ou a rede local caiu. O log no console informará o status.
*   **O log relata "FORMATO_DATA_INVALIDO":** O ficheiro contém datas fora do padrão exigido ou campos corrompidos. Verifique o ficheiro `_FALHAS.csv` gerado na pasta de origem para ver exatamente qual linha causou o erro.
*   **Timeouts constantes na plataforma:** Diminua o limite de EPS para 15 ou 20. O servidor precisa de tempo para executar os nós de roteamento no ThingsBoard.
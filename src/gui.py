import os
import json
import logging
from logging.handlers import RotatingFileHandler
import time
import datetime
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from src import config, utils, engine

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hide()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(600, self.show)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_: self.widget.after_cancel(id_)

    def show(self):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        label = tk.Label(tw, text=self.text, justify='left', background="#2b2b2b",
                         foreground="#ffffff", relief='solid', borderwidth=1, font=("Arial", 10), padx=8, pady=5)
        label.pack(ipadx=1)

    def hide(self):
        tw = self.tooltip_window
        self.tooltip_window = None
        if tw: tw.destroy()


class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        self.text_widget.after(0, self._append_text, self.format(record))

    def _append_text(self, msg):
        self.text_widget.configure(state='normal')
        self.text_widget.insert("end", msg + '\n')
        self.text_widget.configure(state='disabled')
        self.text_widget.see("end")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Telix Data Injector - Pro")
        self.geometry("850x900")
        self.minsize(800, 850)

        self.target_paths = []
        self.scanned_files = []
        self.is_folder = False
        self.stop_event = threading.Event()

        self.setup_ui()
        self.setup_logging()
        self.load_config()

    def create_card(self, parent, title):
        frame = ctk.CTkFrame(parent, corner_radius=10)
        frame.pack(fill="x", pady=(0, 15), padx=5)
        lbl_title = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title.pack(anchor="w", padx=15, pady=(10, 5))
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        return content

    def setup_ui(self):
        main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 1. Servidor
        server_lf = self.create_card(main_frame, "Destino (Thingsboard)")
        self.env_var = tk.StringVar(value="nuvem")
        radio_frame = ctk.CTkFrame(server_lf, fg_color="transparent")
        radio_frame.pack(fill="x", pady=(0, 10))
        rb_nuvem = ctk.CTkRadioButton(radio_frame, text="Nuvem (https://)", variable=self.env_var, value="nuvem",
                                      command=self.toggle_env)
        rb_nuvem.pack(side="left", padx=(0, 20))
        rb_interno = ctk.CTkRadioButton(radio_frame, text="Servidor Interno (http://)", variable=self.env_var,
                                        value="interno", command=self.toggle_env)
        rb_interno.pack(side="left")
        ToolTip(rb_nuvem, "Para plataformas hospedadas na internet, como crvr.telix.com.br")
        ToolTip(rb_interno, "Para acesso local via IP, como 192.168.0.100")

        addr_frame = ctk.CTkFrame(server_lf, fg_color="transparent")
        addr_frame.pack(fill="x")
        self.lbl_protocol = ctk.CTkLabel(addr_frame, text="https://", text_color="#3b8ed0",
                                         font=ctk.CTkFont(weight="bold"))
        self.lbl_protocol.pack(side="left", padx=(0, 5))
        self.url_entry = ctk.CTkEntry(addr_frame, width=350, placeholder_text="crvr.telix.com.br")
        self.url_entry.pack(side="left", fill="x", expand=True)
        ToolTip(self.url_entry, "Endereço do servidor sem barras (/) ou protocolo.")
        self.lbl_port = ctk.CTkLabel(addr_frame, text="Porta:")
        self.port_entry = ctk.CTkEntry(addr_frame, width=80)
        ToolTip(self.port_entry, "Porta de comunicação. Oculto na nuvem.")

        # 2. Configurações
        config_lf = self.create_card(main_frame, "Motor de Inserção (Controle de Tráfego)")
        row1 = ctk.CTkFrame(config_lf, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        lbl_tz = ctk.CTkLabel(row1, text="Fuso Horário (Offset):", width=200, anchor="w")
        lbl_tz.pack(side="left")
        self.tz_entry = ctk.CTkEntry(row1, width=80)
        self.tz_entry.pack(side="left")
        ToolTip(lbl_tz, "Ajuste de hora do sensor. UTC para Brasília = -3.")

        row2 = ctk.CTkFrame(config_lf, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        lbl_eps = ctk.CTkLabel(row2, text="Limite de Leituras (EPS):", width=200, anchor="w")
        lbl_eps.pack(side="left")
        self.eps_entry = ctk.CTkEntry(row2, width=80)
        self.eps_entry.pack(side="left")
        ctk.CTkLabel(row2, text=" (Recomendado: 25 a 50)", text_color="gray").pack(side="left", padx=10)
        ToolTip(self.eps_entry, "Velocidade do envio. Mantenha entre 25 e 50.")

        # 3. Fonte de Dados e Dicionário de Dados
        file_lf = self.create_card(main_frame, "Fonte de Dados e Validação Prévia")
        self.path_label = ctk.CTkLabel(file_lf, text="Nenhum dado selecionado.", text_color="gray")
        self.path_label.pack(anchor="w")
        self.scan_lbl = ctk.CTkLabel(file_lf, text="", font=ctk.CTkFont(weight="bold"))
        self.scan_lbl.pack(anchor="w", pady=(0, 10))

        btn_frame_file = ctk.CTkFrame(file_lf, fg_color="transparent")
        btn_frame_file.pack(side="right")

        btn_format = ctk.CTkButton(btn_frame_file, text="ℹ️ Formato Esperado", fg_color="#17a2b8",
                                   hover_color="#138496", command=self.show_expected_format)
        btn_format.pack(side="left", padx=(0, 15))
        ToolTip(btn_format, "Abre a documentação visual de como as colunas do CSV devem estar estruturadas.")

        btn_clear = ctk.CTkButton(btn_frame_file, text="Limpar", fg_color="transparent", border_width=1,
                                  command=self.clear_selection)
        btn_clear.pack(side="left", padx=(0, 15))
        ToolTip(btn_clear, "Zera a área de trabalho.")

        btn_csv = ctk.CTkButton(btn_frame_file, text="Selecionar CSV", command=self.select_file)
        btn_csv.pack(side="left", padx=5)
        btn_folder = ctk.CTkButton(btn_frame_file, text="Selecionar Pasta", command=self.select_folder)
        btn_folder.pack(side="left", padx=5)

        # 4. HUD
        hud_frame = ctk.CTkFrame(main_frame, corner_radius=10)
        hud_frame.pack(fill="x", pady=(0, 15), padx=5)
        inner_hud = ctk.CTkFrame(hud_frame, fg_color="transparent")
        inner_hud.pack(fill="x", padx=15, pady=15)
        self.lbl_eps = ctk.CTkLabel(inner_hud, text="VELOCIDADE: 0 reg/s",
                                    font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#3b8ed0")
        self.lbl_eps.pack(side="left", expand=True)
        self.lbl_eta = ctk.CTkLabel(inner_hud, text="ETA: --:--:--",
                                    font=ctk.CTkFont(family="Consolas", size=13, weight="bold"))
        self.lbl_eta.pack(side="left", expand=True)
        self.lbl_success = ctk.CTkLabel(inner_hud, text="OK: 0",
                                        font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                                        text_color="#28a745")
        self.lbl_success.pack(side="left", expand=True)
        self.lbl_errors = ctk.CTkLabel(inner_hud, text="FALHAS: 0",
                                       font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                                       text_color="#dc3545")
        self.lbl_errors.pack(side="left", expand=True)

        self.progress = ctk.CTkProgressBar(main_frame, height=12)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(0, 15), padx=5)

        # 5. Ações e Logs
        action_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_frame.pack(fill="x", pady=(0, 15), padx=5)
        self.start_btn = ctk.CTkButton(action_frame, text="▶ INICIAR OPERAÇÃO", fg_color="#28a745",
                                       hover_color="#218838", font=ctk.CTkFont(weight="bold"),
                                       command=self.start_process, state="disabled")
        self.start_btn.pack(side="left", padx=(0, 10))
        self.stop_btn = ctk.CTkButton(action_frame, text="⏹ ABORTAR", fg_color="#dc3545", hover_color="#c82333",
                                      font=ctk.CTkFont(weight="bold"), command=self.stop_process, state="disabled")
        self.stop_btn.pack(side="left")

        log_frame = self.create_card(main_frame, "Console de Operações")
        self.log_text = ctk.CTkTextbox(log_frame, height=200, font=ctk.CTkFont(family="Consolas", size=12),
                                       text_color="#a5d6a7", fg_color="#1e1e1e", state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def toggle_env(self):
        if self.env_var.get() == "nuvem":
            self.lbl_protocol.configure(text="https://")
            self.lbl_port.pack_forget()
            self.port_entry.pack_forget()
        else:
            self.lbl_protocol.configure(text="http://")
            self.lbl_port.pack(side="left", padx=(15, 5))
            self.port_entry.pack(side="left")

    def show_expected_format(self):
        """Janela visual representando o Excel/CSV que o script aceita"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Estrutura do Arquivo de Origem")
        dialog.geometry("1100x250")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)

        lbl_info = ctk.CTkLabel(dialog,
                                text="O arquivo de dados (CSV ou TXT) deve conter EXATAMENTE 14 colunas separadas por vírgula (,).",
                                font=ctk.CTkFont(size=14, weight="bold"))
        lbl_info.pack(pady=15)

        # Simulando uma tabela Excel
        table_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        table_frame.pack(padx=20, pady=5, fill="x")

        # Configura as 14 colunas para terem o mesmo peso e expandirem
        for i in range(14):
            table_frame.grid_columnconfigure(i, weight=1)

        headers = ["Data/Hora", "S1D1", "S1D2", "S2D1", "S2D2", "S3D1", "S3D2", "S4D1", "S4D2", "VBat", "LBat", "RSSI",
                   "SNR", "Extra"]
        example1 = ["25/09/2026 15:32:31", "1.25", "", "0.80", "1.02", "", "", "", "", "12.4", "False", "-85", "10",
                    "0"]
        example2 = ["25/09/2026 16:32:31", "1.26", "", "0.81", "1.01", "", "", "", "", "12.3", "True", "-88", "8", ""]

        # Renderiza Cabeçalhos
        for col, text in enumerate(headers):
            lbl = ctk.CTkLabel(table_frame, text=text, font=ctk.CTkFont(weight="bold"), fg_color="#3b8ed0",
                               text_color="white", corner_radius=0)
            lbl.grid(row=0, column=col, padx=1, pady=1, sticky="nsew", ipady=5)

        # Renderiza Linha 1
        for col, text in enumerate(example1):
            lbl = ctk.CTkLabel(table_frame, text=text if text else "NaN", fg_color="#2b2b2b",
                               text_color="white" if text else "gray", corner_radius=0)
            lbl.grid(row=1, column=col, padx=1, pady=1, sticky="nsew", ipady=5)

        # Renderiza Linha 2
        for col, text in enumerate(example2):
            lbl = ctk.CTkLabel(table_frame, text=text if text else "NaN", fg_color="#1f1f1f",
                               text_color="white" if text else "gray", corner_radius=0)
            lbl.grid(row=2, column=col, padx=1, pady=1, sticky="nsew", ipady=5)

        lbl_note = ctk.CTkLabel(dialog,
                                text="⚠ Notas Importantes:\n• A primeira linha (cabeçalho) é sempre ignorada, mas deve existir.\n• Colunas vazias de sensores serão tratadas como 'NaN' (não nulo) automaticamente.\n• Formato de data obrigatório: DD/MM/YYYY HH:MM:SS (o offset corrige o fuso).",
                                justify="left", text_color="gray")
        lbl_note.pack(anchor="w", padx=20, pady=10)

    def load_config(self):
        defaults = {"env": "nuvem", "url": "crvr.telix.com.br", "port": "8080", "tz": "-3", "eps": "50"}
        if os.path.exists(config.CONFIG_FILE):
            try:
                with open(config.CONFIG_FILE, 'r') as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        self.env_var.set(defaults["env"])
        self.url_entry.insert(0, defaults["url"])
        self.port_entry.insert(0, defaults["port"])
        self.tz_entry.insert(0, defaults["tz"])
        self.eps_entry.insert(0, defaults["eps"])
        self.toggle_env()

    def save_config(self):
        conf = {
            "env": self.env_var.get(), "url": self.url_entry.get().strip(),
            "port": self.port_entry.get().strip(), "tz": self.tz_entry.get().strip(),
            "eps": self.eps_entry.get().strip()
        }
        try:
            with open(config.CONFIG_FILE, 'w') as f:
                json.dump(conf, f)
        except Exception:
            pass

    def setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        if logger.hasHandlers(): logger.handlers.clear()

        gui_handler = TextHandler(self.log_text)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s: %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(gui_handler)

        file_handler = RotatingFileHandler("historico_reinsercao.log", maxBytes=5 * 1024 * 1024, backupCount=3,
                                           encoding='utf-8')
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(file_handler)

    def clear_selection(self):
        self.target_paths, self.scanned_files, self.is_folder = [], [], False
        self.path_label.configure(text="Nenhum dado selecionado.")
        self.scan_lbl.configure(text="")
        self.start_btn.configure(state="disabled")

        self.lbl_eps.configure(text="VELOCIDADE: 0 reg/s")
        self.lbl_eta.configure(text="ETA: --:--:--")
        self.lbl_success.configure(text="OK: 0")
        self.lbl_errors.configure(text="FALHAS: 0")
        self.progress.set(0)

        self.log_text.configure(state='normal')
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state='disabled')
        with config.state_lock: config.state.update(
            {"processed_count": 0, "success_count": 0, "error_count": 0, "total_target": 0})

    def trigger_scan(self, paths, is_folder):
        self.scan_lbl.configure(text="⏳ Analisando integridade...", text_color="orange")
        self.start_btn.configure(state="disabled")
        threading.Thread(target=utils.scan_targets_async, args=(paths, is_folder, self.on_scan_complete),
                         daemon=True).start()

    def select_file(self):
        filename = filedialog.askopenfilename(title='Selecione o CSV', filetypes=[('CSV', '*.csv *.txt')])
        if filename:
            self.target_paths, self.is_folder = [filename], False
            self.path_label.configure(text=f"Arquivo: {os.path.basename(filename)}", text_color="white")
            self.trigger_scan(self.target_paths, self.is_folder)

    def select_folder(self):
        folder = filedialog.askdirectory(title='Selecione a pasta')
        if folder:
            self.target_paths, self.is_folder = [folder], True
            self.path_label.configure(text=f"Pasta: {folder}", text_color="white")
            self.trigger_scan(self.target_paths, self.is_folder)

    def on_scan_complete(self, files_scanned, total_lines, invalid_lines, msg):
        def update():
            if msg == "OK":
                self.scanned_files = files_scanned
                color = "#dc3545" if invalid_lines > 0 else "#28a745"
                self.scan_lbl.configure(text=f"✔ {total_lines} linhas prontas | {invalid_lines} formatos corrompidos.",
                                        text_color=color)
                self.start_btn.configure(state="normal")

                config.state["total_target"] = total_lines
                for f in files_scanned:
                    ckpt = utils.get_checkpoint(f)
                    if ckpt > 1 and messagebox.askyesno("Checkpoint",
                                                        f"Retomar {os.path.basename(f)} da linha {ckpt}?"):
                        config.state["total_target"] -= (ckpt - 1)
                    elif ckpt > 1:
                        utils.manage_checkpoint(f, clear=True)
            else:
                self.scan_lbl.configure(text=msg, text_color="#dc3545")

        self.after(0, update)

    def stop_process(self):
        self.stop_event.set()
        self.stop_btn.configure(state="disabled")

    def update_hud(self):
        if not config.state["is_running"]: return
        with config.state_lock:
            elapsed = time.time() - config.state["start_time"]
            processed = config.state["processed_count"]
            eps = int(processed / elapsed) if elapsed > 0 else 0

            eta_str = "--:--:--"
            if eps > 0 and (config.state["total_target"] - processed) > 0:
                eta_str = str(datetime.timedelta(seconds=int((config.state["total_target"] - processed) / eps)))

            self.lbl_eps.configure(text=f"VELOCIDADE: {eps} reg/s")
            self.lbl_eta.configure(text=f"ETA: {eta_str}")
            self.lbl_success.configure(text=f"OK: {config.state['success_count']}")
            self.lbl_errors.configure(text=f"FALHAS: {config.state['error_count']}")

            progress_val = (processed / config.state["total_target"]) if config.state["total_target"] > 0 else 0
            self.progress.set(min(1.0, progress_val))

        self.after(500, self.update_hud)

    def process_finished(self, files_processed):
        def reset_ui():
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.update_hud()
            if not self.stop_event.is_set() and files_processed:
                if config.state["error_count"] > 0:
                    messagebox.showwarning("Atenção", "Concluído com falhas exportadas no DLQ.")
                else:
                    messagebox.showinfo("Sucesso", "Concluído sem erros de rede.")

        self.after(0, reset_ui)

    def start_process(self):
        try:
            tz, target_eps = int(self.tz_entry.get()), int(self.eps_entry.get())
        except ValueError:
            messagebox.showerror("Erro", "Valores numéricos inválidos.")
            return

        self.save_config()
        base_url = f"https://{self.url_entry.get().strip()}" if self.env_var.get() == "nuvem" else f"http://{self.url_entry.get().strip()}:{self.port_entry.get().strip()}"

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.stop_event.clear()

        with config.state_lock:
            config.state.update(
                {"is_running": True, "start_time": time.time(), "processed_count": 0, "success_count": 0,
                 "error_count": 0})
        self.log_text.configure(state='normal');
        self.log_text.delete("1.0", "end");
        self.log_text.configure(state='disabled')
        self.progress.set(0)

        self.after(500, self.update_hud)
        threading.Thread(target=engine.orchestrate_queue,
                         args=(self.scanned_files, base_url, tz, target_eps, self.process_finished, self.stop_event),
                         daemon=True).start()
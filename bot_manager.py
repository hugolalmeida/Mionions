import customtkinter as ctk
from tkinter import messagebox, filedialog
import subprocess
import os
import sys
import winreg
import json
from datetime import datetime
import threading
import pystray
from PIL import Image, ImageDraw

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BOT_SCRIPT = "Disbot_Mionions.py"
BOT_NAME = "Mionions Bot"
PID_FILE = "mionions_bot.pid"
CONFIG_FILE = "bot_config.json"
REG_KEY_NAME = "MionionsBot"


class LogWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"📋 Logs — {BOT_NAME}")
        self.geometry("820x500")

        self.log_text = ctk.CTkTextbox(self, width=800, height=440, font=("Consolas", 11))
        self.log_text.pack(padx=10, pady=10)

        clear_btn = ctk.CTkButton(self, text="🗑️ Limpar Logs", command=self.clear_logs,
                                  fg_color="#e74c3c", hover_color="#c0392b")
        clear_btn.pack(pady=5)

        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

    def clear_logs(self):
        self.log_text.delete("1.0", "end")
        self.add_log("Logs limpos.")


class BotManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"🤖 {BOT_NAME} Manager")
        self.geometry("500x540")
        self.resizable(False, False)

        self.bot_process = None
        self.is_running = False
        self.is_detached = False

        self.log_window = LogWindow(self)
        self.log_window.withdraw()

        self.load_config()
        self.setup_ui()
        self.check_autostart_status()
        self.cleanup_orphan_processes()
        self.check_detached_bot()
        self.create_tray_icon()

        # Inicia minimizado na bandeja
        self.withdraw()

        if not self.is_running:
            self.after(1000, self.start_bot)

        self.after(2000, self.show_tray_notification)

    # ─── Config ──────────────────────────────────────────────────────────────

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    self.config = json.load(f)
            else:
                self.config = {"auto_restart": False, "restart_interval_hours": 24}
        except Exception:
            self.config = {"auto_restart": False, "restart_interval_hours": 24}

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log(f"Erro ao salvar config: {e}")

    # ─── UI ──────────────────────────────────────────────────────────────────

    def setup_ui(self):
        ctk.CTkLabel(self, text=f"🤖 {BOT_NAME} Manager",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=18)

        self.status_label = ctk.CTkLabel(self, text="⭕ Desligado",
                                         font=ctk.CTkFont(size=15),
                                         text_color="#e74c3c")
        self.status_label.pack(pady=6)

        # Botões principais
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=12)

        self.start_btn = ctk.CTkButton(btn_frame, text="▶ Iniciar", command=self.start_bot,
                                       width=140, height=40,
                                       fg_color="#27ae60", hover_color="#229954")
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ctk.CTkButton(btn_frame, text="⏹ Parar", command=self.stop_bot,
                                      width=140, height=40,
                                      fg_color="#e74c3c", hover_color="#c0392b",
                                      state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=5)

        self.restart_btn = ctk.CTkButton(btn_frame, text="🔄 Reiniciar", command=self.restart_bot,
                                         width=140, height=40,
                                         fg_color="#f39c12", hover_color="#e67e22",
                                         state="disabled")
        self.restart_btn.grid(row=0, column=2, padx=5)

        # Botões de log
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(pady=8)

        ctk.CTkButton(log_frame, text="📋 Ver Logs", command=self.show_logs,
                      width=140, height=35,
                      fg_color="#3498db", hover_color="#2980b9").grid(row=0, column=0, padx=5)

        ctk.CTkButton(log_frame, text="💾 Exportar Log", command=self.export_log,
                      width=140, height=35,
                      fg_color="#9b59b6", hover_color="#8e44ad").grid(row=0, column=1, padx=5)

        # Configurações
        config_frame = ctk.CTkFrame(self)
        config_frame.pack(pady=14, padx=20, fill="x")

        ctk.CTkLabel(config_frame, text="⚙️ Configurações",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=8)

        self.autostart_var = ctk.BooleanVar()
        ctk.CTkSwitch(config_frame, text="💻 Iniciar com Windows",
                      variable=self.autostart_var,
                      command=self.toggle_autostart).pack(pady=5, padx=20, anchor="w")

        restart_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        restart_frame.pack(pady=5, padx=20, fill="x")

        self.auto_restart_var = ctk.BooleanVar(value=self.config.get("auto_restart", False))
        ctk.CTkSwitch(restart_frame, text="🔁 Reiniciar a cada:",
                      variable=self.auto_restart_var,
                      command=self.toggle_auto_restart).pack(side="left")

        self.interval_var = ctk.IntVar(value=self.config.get("restart_interval_hours", 24))
        ctk.CTkEntry(restart_frame, width=50, textvariable=self.interval_var).pack(side="left", padx=5)
        ctk.CTkLabel(restart_frame, text="horas").pack(side="left")

        ctk.CTkLabel(self, text="✨ Fechar esta janela mantém o bot rodando na bandeja",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=10)

        self.log(f"{BOT_NAME} Manager iniciado")
        self.log(f"Script: {os.path.abspath(BOT_SCRIPT)}")

    # ─── Log ─────────────────────────────────────────────────────────────────

    def log(self, message):
        self.log_window.add_log(message)

    def show_logs(self):
        self.log_window.deiconify()
        self.log_window.lift()

    def export_log(self):
        content = self.log_window.log_text.get("1.0", "end")
        if not content.strip():
            messagebox.showwarning("Aviso", "Nenhum log para exportar.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log", "*.log"), ("Texto", "*.txt")],
            initialfile=f"mionions_bot_{timestamp}.log",
            title="Exportar Log",
        )
        if dest:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content)
            self.log(f"Log exportado: {dest}")
            messagebox.showinfo("Sucesso", f"Log exportado:\n{dest}")

    # ─── Bandeja ──────────────────────────────────────────────────────────────

    def create_tray_icon(self):
        img = Image.new("RGB", (64, 64), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        draw.ellipse((6, 6, 58, 58), fill=(88, 101, 242))   # cor roxa do Discord
        draw.ellipse((20, 20, 44, 44), fill=(30, 30, 30))

        menu = (
            pystray.MenuItem("Mostrar Gerenciador", self.show_window),
            pystray.MenuItem("Parar Bot", self.stop_bot,
                             enabled=lambda item: self.is_running),
            pystray.MenuItem("Fechar Gerenciador", self.exit_from_tray),
        )
        self.tray_icon = pystray.Icon(REG_KEY_NAME, img, BOT_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def show_tray_notification(self):
        try:
            self.tray_icon.notify(
                title=BOT_NAME,
                message="Gerenciador rodando na bandeja. Clique no ícone para abrir.",
            )
        except Exception:
            pass

    def exit_from_tray(self, icon=None, item=None):
        if self.is_running:
            self.stop_bot()
        self.tray_icon.stop()
        self.destroy()

    # ─── Processos ────────────────────────────────────────────────────────────

    def cleanup_orphan_processes(self):
        try:
            import psutil
            script_abs = os.path.abspath(BOT_SCRIPT)
            killed = 0
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                    if len(cmdline) >= 2 and "python" in cmdline[0].lower():
                        if script_abs.lower() in " ".join(cmdline).lower():
                            proc.kill()
                            killed += 1
                            self.log(f"Processo órfão eliminado (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            if killed:
                self.log(f"{killed} processo(s) órfão(s) eliminado(s)")
        except ImportError:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception as e:
            self.log(f"Erro ao limpar órfãos: {e}")

    def check_detached_bot(self):
        if not os.path.exists(PID_FILE):
            return
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            self.is_running = True
            self.is_detached = True
            self._set_ui_running()
            self.log(f"Bot detectado rodando (PID: {pid})")
        except Exception:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)

    def start_bot(self):
        if self.is_running:
            return
        try:
            self.log(f"Iniciando {BOT_NAME}...")
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.bot_process = subprocess.Popen(
                [sys.executable, "-u", BOT_SCRIPT],
                creationflags=flags,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
                universal_newlines=True,
            )
            with open(PID_FILE, "w") as f:
                f.write(str(self.bot_process.pid))

            self.is_running = True
            self.is_detached = True
            self._set_ui_running()
            self.log(f"Bot iniciado (PID: {self.bot_process.pid})")
            self.log("Abra 'Ver Logs' para acompanhar a atividade.")

            threading.Thread(target=self._read_bot_output, daemon=True).start()

            if self.auto_restart_var.get():
                self.schedule_auto_restart()

        except Exception as e:
            self.log(f"Erro ao iniciar: {e}")
            self._set_ui_stopped()

    def _read_bot_output(self):
        import queue, time

        def enqueue(pipe, q):
            try:
                for line in iter(pipe.readline, ""):
                    if line:
                        q.put(line)
                pipe.close()
            except Exception:
                pass

        out_q, err_q = queue.Queue(), queue.Queue()
        threading.Thread(target=enqueue, args=(self.bot_process.stdout, out_q), daemon=True).start()
        threading.Thread(target=enqueue, args=(self.bot_process.stderr, err_q), daemon=True).start()

        while self.is_running and self.bot_process:
            for q, prefix in ((out_q, "[BOT]"), (err_q, "[ERR]")):
                try:
                    while True:
                        line = q.get_nowait().strip()
                        if line:
                            self.log(f"{prefix} {line}")
                except queue.Empty:
                    pass

            if self.bot_process.poll() is not None:
                time.sleep(0.3)
                for q, prefix in ((out_q, "[BOT]"), (err_q, "[ERR]")):
                    try:
                        while True:
                            line = q.get_nowait().strip()
                            if line:
                                self.log(f"{prefix} {line}")
                    except queue.Empty:
                        pass
                self.log("Bot encerrado.")
                self.is_running = False
                self.is_detached = False
                self.after(0, self._set_ui_stopped)
                if os.path.exists(PID_FILE):
                    os.remove(PID_FILE)
                break

            time.sleep(0.1)

    def stop_bot(self, icon=None, item=None):
        if not self.is_running:
            return
        try:
            self.log("Parando bot...")
            if os.path.exists(PID_FILE):
                with open(PID_FILE) as f:
                    pid = int(f.read().strip())
                try:
                    if sys.platform == "win32":
                        import ctypes
                        h = ctypes.windll.kernel32.OpenProcess(1, False, pid)
                        ctypes.windll.kernel32.TerminateProcess(h, 0)
                        ctypes.windll.kernel32.CloseHandle(h)
                    else:
                        import signal
                        os.kill(pid, signal.SIGTERM)
                    self.log(f"Bot parado (PID: {pid})")
                except ProcessLookupError:
                    self.log("Processo já havia encerrado.")
                finally:
                    if os.path.exists(PID_FILE):
                        os.remove(PID_FILE)

            self.is_running = False
            self.is_detached = False
            self._set_ui_stopped()

        except Exception as e:
            self.log(f"Erro ao parar: {e}")

    def restart_bot(self):
        self.log("Reiniciando bot...")
        self.stop_bot()
        self.after(2000, self.start_bot)

    # ─── UI helpers ──────────────────────────────────────────────────────────

    def _set_ui_running(self):
        self.status_label.configure(text="🟢 Ligado", text_color="#27ae60")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.restart_btn.configure(state="normal")

    def _set_ui_stopped(self):
        self.status_label.configure(text="⭕ Desligado", text_color="#e74c3c")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.restart_btn.configure(state="disabled")

    # ─── Auto-restart ────────────────────────────────────────────────────────

    def schedule_auto_restart(self):
        if self.auto_restart_var.get() and self.is_running:
            ms = self.interval_var.get() * 3600 * 1000
            self.log(f"Próximo restart automático em {self.interval_var.get()}h")
            self.after(ms, self._do_auto_restart)

    def _do_auto_restart(self):
        if self.auto_restart_var.get() and self.is_running:
            self.log("Executando restart automático agendado...")
            self.restart_bot()

    def toggle_auto_restart(self):
        self.config["auto_restart"] = self.auto_restart_var.get()
        self.config["restart_interval_hours"] = self.interval_var.get()
        self.save_config()
        if self.auto_restart_var.get() and self.is_running:
            self.schedule_auto_restart()

    # ─── Autostart Windows ───────────────────────────────────────────────────

    def check_autostart_status(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, REG_KEY_NAME)
                self.autostart_var.set(True)
            except FileNotFoundError:
                self.autostart_var.set(False)
            finally:
                winreg.CloseKey(key)
        except Exception:
            self.autostart_var.set(False)

    def toggle_autostart(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            if self.autostart_var.get():
                manager_path = os.path.abspath(__file__)
                pythonw = sys.executable.replace("python.exe", "pythonw.exe")
                exe = pythonw if os.path.exists(pythonw) else sys.executable
                winreg.SetValueEx(key, REG_KEY_NAME, 0, winreg.REG_SZ,
                                  f'"{exe}" "{manager_path}"')
                self.log("Iniciar com Windows: ATIVADO")
            else:
                try:
                    winreg.DeleteValue(key, REG_KEY_NAME)
                    self.log("Iniciar com Windows: DESATIVADO")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            self.log(f"Erro no autostart: {e}")
            messagebox.showerror("Erro", f"Não foi possível configurar autostart:\n{e}")

    # ─── Fechar ───────────────────────────────────────────────────────────────

    def on_closing(self):
        if self.is_running:
            self.withdraw()
            self.log("Gerenciador ocultado na bandeja. Bot continua rodando.")
        else:
            self.tray_icon.stop()
            self.destroy()


def main():
    app = BotManager()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()

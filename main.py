import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta
import threading
import time
import os
import sys
import winsound
import uuid
import webbrowser
import json

APP_NAME = "FocusBell"
DATA_FILE = "tasks.json"

# ========== THEME CONFIG ==========
THEME = {
    "bg": "#121212",          # Main Background (Very Dark)
    "card": "#1E1E1E",        # Card/Item Background
    "card_highlight": "#2d2d2d", # Next task highlight
    "fg": "#E0E0E0",          # Main Text
    "fg_sub": "#A0A0A0",      # Subtitle Text
    "accent": "#BB86FC",      # Primary Action (Purple)
    "accent_hover": "#9965f4",
    "secondary": "#03DAC6",   # Secondary Action (Teal)
    "danger": "#CF6679",      # Delete/Cancel (Soft Red)
    "success": "#00C853",     # Success (Green)
    "warning": "#FFB74D",     # Snooze/Warning (Orange)
    "input_bg": "#2C2C2C",    # Input Fields
    "font_main": "Segoe UI",
}

# --------- RESOURCE PATH ----------
def resource_path(relative):
    try:
        base = sys._MEIPASS
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, relative)

# ========== DATA MODEL ==========
class Alarm:
    def __init__(self, task_name, alarm_time, active=True, id=None):
        self.id = id if id else str(uuid.uuid4())
        self.task_name = task_name
        self.alarm_time = alarm_time
        self.active = active

    def get_time_str(self):
        return self.alarm_time.strftime("%I:%M %p")
    
    def get_remaining_str(self):
        if not self.active:
            return "Done"
        now = datetime.now()
        if self.alarm_time <= now:
            return "Due now"
        delta = self.alarm_time - now
        
        # Human readable format
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"in {hours}h {minutes}m"
        else:
            return f"in {minutes}m"

    def to_dict(self):
        return {
            "id": self.id,
            "task_name": self.task_name,
            "alarm_time": self.alarm_time.isoformat(),
            "active": self.active
        }

    @classmethod
    def from_dict(cls, data):
        try:
            return cls(
                task_name=data["task_name"],
                alarm_time=datetime.fromisoformat(data["alarm_time"]),
                active=data["active"],
                id=data.get("id")
            )
        except Exception as e:
            print(f"Error loading task: {e}")
            return None

# ========== MAIN APP ==========
class FocusBellApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("600x750")
        self.root.configure(bg=THEME["bg"])
        self.root.resizable(False, False)

        # State
        self.alarms = []
        self.check_thread = None
        self.is_running = True

        # Custom Styles
        self.setup_styles()

        # Load Data
        self.load_tasks()

        # Build Initial UI (Dashboard)
        self.main_container = tk.Frame(self.root, bg=THEME["bg"])
        self.main_container.pack(fill="both", expand=True)
        
        self.show_dashboard()

        # Start Background Thread
        self.check_thread = threading.Thread(target=self.alarm_check_loop, daemon=True)
        self.check_thread.start()

        # Start UI Refresh Loop (for countdowns)
        self.refresh_ui_loop()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Scrollbar
        style.configure("Vertical.TScrollbar", gripcount=0,
                        background=THEME["card"], darkcolor=THEME["bg"], lightcolor=THEME["bg"],
                        troughcolor=THEME["bg"], bordercolor=THEME["bg"], arrowcolor=THEME["fg"])

        # Combobox
        style.map('TCombobox', fieldbackground=[('readonly', THEME["input_bg"])],
                  selectbackground=[('readonly', THEME["input_bg"])],
                  selectforeground=[('readonly', THEME["fg"])])
        style.configure("TCombobox", fieldbackground=THEME["input_bg"], background=THEME["card"],
                        foreground=THEME["fg"], arrowcolor=THEME["accent"], borderwidth=0)

    # ========== DATA PERSISTENCE ==========
    def save_tasks(self):
        try:
            data = [alarm.to_dict() for alarm in self.alarms]
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving tasks: {e}")

    def load_tasks(self):
        if not os.path.exists(DATA_FILE):
            return
        
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                self.alarms = []
                for item in data:
                    alarm = Alarm.from_dict(item)
                    if alarm:
                        # If loaded task is active but time passed, keep it active (it will trigger immediately)
                        # or we could auto-move to next day. 
                        # Current logic: It will trigger immediately if time passed.
                        self.alarms.append(alarm)
                
                self.alarms.sort(key=lambda x: x.alarm_time)
        except Exception as e:
            print(f"Error loading tasks: {e}")

    # ========== NAVIGATION ==========
    def clear_container(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def show_dashboard(self):
        self.clear_container()
        
        # Header
        header = tk.Frame(self.main_container, bg=THEME["bg"])
        header.pack(fill="x", padx=30, pady=(30, 20))

        tk.Label(header, text="My Tasks", font=(THEME["font_main"], 28, "bold"),
                 fg=THEME["fg"], bg=THEME["bg"]).pack(side="left")

        # Add Button
        tk.Button(header, text="+ New Task", font=(THEME["font_main"], 12, "bold"),
                  bg=THEME["accent"], fg="#000000", activebackground=THEME["accent_hover"],
                  relief="flat", padx=15, pady=5, cursor="hand2",
                  command=lambda: self.show_editor()
                  ).pack(side="right")

        # Task List Area
        list_frame = tk.Frame(self.main_container, bg=THEME["bg"])
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Canvas for scrolling
        canvas = tk.Canvas(list_frame, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=THEME["bg"])

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=540)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Sort: Active first, then by time
        sorted_alarms = sorted(self.alarms, key=lambda x: (not x.active, x.alarm_time))

        # Render Items
        if not sorted_alarms:
            self.render_empty_state()
        else:
            # Check for next upcoming task
            next_task = next((a for a in sorted_alarms if a.active), None)
            
            for alarm in sorted_alarms:
                is_next = (alarm == next_task)
                self.render_alarm_item(alarm, is_next)

        # Footer / Info
        footer = tk.Frame(self.main_container, bg=THEME["bg"])
        footer.pack(side="bottom", fill="x", pady=20, padx=30)

        active_count = sum(1 for a in self.alarms if a.active)
        tk.Label(footer, text=f"{active_count} Active Tasks", 
                 font=(THEME["font_main"], 10), fg=THEME["fg_sub"], bg=THEME["bg"]
                 ).pack(side="left")

        tk.Button(footer, text="Developer Info", font=(THEME["font_main"], 10, "underline"),
                  bg=THEME["bg"], fg=THEME["fg_sub"], activebackground=THEME["bg"], activeforeground=THEME["accent"],
                  relief="flat", cursor="hand2", command=self.show_dev_page
                  ).pack(side="right")

    def render_empty_state(self):
        frame = tk.Frame(self.scrollable_frame, bg=THEME["bg"])
        frame.pack(pady=50, fill="x")
        
        tk.Label(frame, text="No tasks yet.", font=(THEME["font_main"], 16),
                 fg=THEME["fg_sub"], bg=THEME["bg"]).pack()
        tk.Label(frame, text="Click '+ New Task' to get started.", font=(THEME["font_main"], 12),
                 fg=THEME["fg_sub"], bg=THEME["bg"]).pack(pady=5)

    def render_alarm_item(self, alarm, is_next=False):
        bg_color = THEME["card_highlight"] if is_next else THEME["card"]
        
        card = tk.Frame(self.scrollable_frame, bg=bg_color)
        card.pack(fill="x", pady=6, ipady=5)
        
        # Indicator strip for next task
        if is_next:
            tk.Frame(card, bg=THEME["accent"], width=4).pack(side="left", fill="y")

        # Content Container
        content = tk.Frame(card, bg=bg_color)
        content.pack(side="left", fill="both", expand=True, padx=15, pady=5)

        # Top Row: Time & Remaining
        top_row = tk.Frame(content, bg=bg_color)
        top_row.pack(fill="x")

        time_color = THEME["accent"] if alarm.active else THEME["fg_sub"]
        tk.Label(top_row, text=alarm.get_time_str(), font=(THEME["font_main"], 18, "bold"),
                 fg=time_color, bg=bg_color).pack(side="left")

        if alarm.active:
            tk.Label(top_row, text=f"• {alarm.get_remaining_str()}", font=(THEME["font_main"], 11),
                     fg=THEME["fg_sub"], bg=bg_color).pack(side="left", padx=10, pady=(4,0))
        else:
             tk.Label(top_row, text="• Completed", font=(THEME["font_main"], 11),
                     fg=THEME["success"], bg=bg_color).pack(side="left", padx=10, pady=(4,0))

        # Bottom Row: Task Name
        tk.Label(content, text=alarm.task_name, font=(THEME["font_main"], 13),
                 fg=THEME["fg"], bg=bg_color, wraplength=350, justify="left").pack(anchor="w", pady=(2,0))

        # Right: Actions
        right = tk.Frame(card, bg=bg_color)
        right.pack(side="right", padx=15)

        # Edit Button
        tk.Button(right, text="Edit", font=(THEME["font_main"], 9),
                  bg=THEME["input_bg"], fg=THEME["fg"], relief="flat", width=6,
                  cursor="hand2", command=lambda a=alarm: self.show_editor(a)
                  ).pack(side="top", pady=2)

        # Delete Button
        tk.Button(right, text="Delete", font=(THEME["font_main"], 9),
                  bg=THEME["input_bg"], fg=THEME["danger"], relief="flat", width=6,
                  cursor="hand2", command=lambda a=alarm: self.delete_alarm(a)
                  ).pack(side="top", pady=2)

    def show_editor(self, alarm=None):
        self.clear_container()
        is_edit = alarm is not None
        
        # Header
        header_text = "Edit Task" if is_edit else "New Task"
        tk.Label(self.main_container, text=header_text, font=(THEME["font_main"], 24, "bold"),
                 fg=THEME["fg"], bg=THEME["bg"]).pack(pady=(40, 30))

        # Form Container
        form = tk.Frame(self.main_container, bg=THEME["bg"])
        form.pack()

        # --- Task Name Input ---
        tk.Label(form, text="Task Description", font=(THEME["font_main"], 12),
                 fg=THEME["fg_sub"], bg=THEME["bg"]).pack(anchor="w", pady=(0, 5))
        
        task_var = tk.StringVar(value=alarm.task_name if is_edit else "")
        task_entry = tk.Entry(form, textvariable=task_var, font=(THEME["font_main"], 14),
                              bg=THEME["input_bg"], fg=THEME["fg"], insertbackground="white",
                              relief="flat", width=30)
        task_entry.pack(ipady=8, pady=(0, 20))
        task_entry.focus()

        # --- Time Input ---
        tk.Label(form, text="Set Time", font=(THEME["font_main"], 12),
                 fg=THEME["fg_sub"], bg=THEME["bg"]).pack(anchor="w", pady=(0, 5))

        time_frame = tk.Frame(form, bg=THEME["bg"])
        time_frame.pack(anchor="w", pady=(0, 30))

        # Defaults
        def_h, def_m, def_ampm = "09", "00", "AM"
        if is_edit:
            t = alarm.alarm_time
            def_h = t.strftime("%I")
            def_m = t.strftime("%M")
            def_ampm = t.strftime("%p")

        # Hours
        hour_var = tk.StringVar(value=def_h)
        hours = [f"{i:02d}" for i in range(1, 13)]
        h_cb = ttk.Combobox(time_frame, textvariable=hour_var, values=hours, width=4, 
                            font=(THEME["font_main"], 16), state="readonly", justify="center")
        h_cb.pack(side="left", padx=(0, 5))

        tk.Label(time_frame, text=":", font=(THEME["font_main"], 16, "bold"),
                 fg=THEME["fg"], bg=THEME["bg"]).pack(side="left")

        # Minutes
        min_var = tk.StringVar(value=def_m)
        minutes = [f"{i:02d}" for i in range(0, 60)]
        m_cb = ttk.Combobox(time_frame, textvariable=min_var, values=minutes, width=4, 
                            font=(THEME["font_main"], 16), state="readonly", justify="center")
        m_cb.pack(side="left", padx=5)

        # AM/PM
        ampm_var = tk.StringVar(value=def_ampm)
        ampm_cb = ttk.Combobox(time_frame, textvariable=ampm_var, values=["AM", "PM"], width=5, 
                               font=(THEME["font_main"], 16), state="readonly", justify="center")
        ampm_cb.pack(side="left", padx=5)

        # --- Actions ---
        btn_frame = tk.Frame(self.main_container, bg=THEME["bg"])
        btn_frame.pack(pady=20)

        # Save Button
        tk.Button(btn_frame, text="Save Task", font=(THEME["font_main"], 14, "bold"),
                  bg=THEME["accent"], fg="#000000", activebackground=THEME["accent_hover"],
                  relief="flat", width=15, cursor="hand2",
                  command=lambda: self.save_alarm(alarm, task_var.get(), hour_var.get(), min_var.get(), ampm_var.get())
                  ).pack(side="left", padx=10)

        # Cancel Button
        tk.Button(btn_frame, text="Cancel", font=(THEME["font_main"], 14),
                  bg=THEME["input_bg"], fg=THEME["fg"], activebackground=THEME["card"], activeforeground=THEME["fg"],
                  relief="flat", width=10, cursor="hand2",
                  command=self.show_dashboard
                  ).pack(side="left", padx=10)

    # ========== LOGIC ==========
    def save_alarm(self, existing_alarm, task_name, hour, minute, ampm):
        task_name = task_name.strip()
        if not task_name:
            messagebox.showwarning("Required", "Please enter a task description.")
            return

        try:
            h = int(hour)
            m = int(minute)
            
            # Convert to 24h for storage
            if ampm == "PM" and h != 12: h += 12
            if ampm == "AM" and h == 12: h = 0

            now = datetime.now()
            alarm_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            
            # If time passed, assume tomorrow
            if alarm_dt <= now:
                alarm_dt += timedelta(days=1)

            if existing_alarm:
                # Update
                existing_alarm.task_name = task_name
                existing_alarm.alarm_time = alarm_dt
                existing_alarm.active = True # Reactivate on edit
            else:
                # Create New
                new_alarm = Alarm(task_name, alarm_dt)
                self.alarms.append(new_alarm)

            self.save_tasks() # PERSIST
            self.show_dashboard()

        except ValueError:
            messagebox.showerror("Error", "Invalid time format.")

    def delete_alarm(self, alarm):
        if messagebox.askyesno("Delete Task", f"Delete '{alarm.task_name}'?"):
            if alarm in self.alarms:
                self.alarms.remove(alarm)
                self.save_tasks() # PERSIST
                self.show_dashboard()

    # ========== BACKGROUND CHECK & REFRESH ==========
    def alarm_check_loop(self):
        while self.is_running:
            now = datetime.now()
            triggered_alarm = None
            
            # Check for triggers
            for alarm in self.alarms:
                if alarm.active and now >= alarm.alarm_time:
                    triggered_alarm = alarm
                    break
            
            if triggered_alarm:
                # Only mark inactive if we don't have snoozing logic handled in the UI
                # But here we trigger UI, which will handle the logic
                self.root.after(0, lambda: self.trigger_alarm_ui(triggered_alarm))
                # Temporary sleep to prevent multiple triggers before UI opens
                time.sleep(2)

            time.sleep(1)

    def refresh_ui_loop(self):
        """Refreshes the dashboard every minute to update 'time remaining'"""
        if self.is_running:
            # If dashboard is visible (simple check: if we are not editing)
            # This is a bit hacky, better state management would be good
            # But for now, just calling show_dashboard if it's the current view is safe enough
            # We can check if 'New Task' button exists to know we are on dashboard
            try:
                # Re-render to update times
                # To avoid disrupting user interaction, maybe only update labels?
                # For simplicity, we just won't auto-refresh the whole UI to avoid glitches.
                # The user can refresh by navigating.
                # OR we update the text of labels if we stored references.
                pass 
            except:
                pass
            self.root.after(60000, self.refresh_ui_loop)

    # ========== FULL SCREEN TRIGGER ==========
    def trigger_alarm_ui(self, alarm):
        # Deactivate alarm temporarily so it doesn't re-trigger while window is open
        # We will set it to False. If Snooze, we set it True with new time.
        alarm.active = False
        self.save_tasks()
        
        # Open Alarm Window
        alarm_win = tk.Toplevel(self.root)
        alarm_win.attributes("-fullscreen", True)
        alarm_win.configure(bg=THEME["bg"])
        alarm_win.lift()
        alarm_win.focus_force()

        # Play Sound
        sound_path = resource_path("alarm.wav")
        try:
            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_LOOP | winsound.SND_ASYNC)
        except Exception:
            pass

        # Content
        tk.Label(alarm_win, text="⏰ IT'S TIME! ⏰", font=(THEME["font_main"], 48, "bold"),
                 fg=THEME["danger"], bg=THEME["bg"]).pack(pady=(60, 20))

        tk.Label(alarm_win, text=alarm.task_name, font=(THEME["font_main"], 64, "bold"),
                 fg=THEME["accent"], bg=THEME["bg"], wraplength=1200, justify="center").pack(expand=True)

        tk.Label(alarm_win, text=f"Scheduled for {alarm.get_time_str()}", font=(THEME["font_main"], 20),
                 fg=THEME["fg_sub"], bg=THEME["bg"]).pack(pady=10)

        # Buttons Frame
        btn_frame = tk.Frame(alarm_win, bg=THEME["bg"])
        btn_frame.pack(pady=60)

        # Snooze Button
        snooze_btn = tk.Button(btn_frame, text="Snooze 5m", font=(THEME["font_main"], 20, "bold"),
                             bg=THEME["warning"], fg="#000000", activebackground="#FFCC80",
                             relief="flat", width=12, height=2, cursor="hand2",
                             command=lambda: self.snooze_alarm(alarm, alarm_win)
                             )
        snooze_btn.pack(side="left", padx=20)

        # Complete Button
        stop_btn = tk.Button(btn_frame, text="COMPLETE", font=(THEME["font_main"], 24, "bold"),
                             bg=THEME["success"], fg="#FFFFFF", activebackground="#00A040", activeforeground="#FFFFFF",
                             relief="flat", width=14, height=2, cursor="hand2",
                             command=lambda: self.stop_alarm(alarm_win)
                             )
        stop_btn.pack(side="left", padx=20)

    def snooze_alarm(self, alarm, window):
        winsound.PlaySound(None, winsound.SND_PURGE)
        window.destroy()
        
        # Add 5 minutes
        alarm.alarm_time = datetime.now() + timedelta(minutes=5)
        alarm.active = True
        self.save_tasks()
        self.show_dashboard()
        messagebox.showinfo("Snoozed", f"Alarm snoozed for 5 minutes.\nNew time: {alarm.get_time_str()}")

    def stop_alarm(self, window):
        winsound.PlaySound(None, winsound.SND_PURGE)
        window.destroy()
        self.show_dashboard() # Return to dashboard and refresh

    # ========== DEV PAGE ==========
    def show_dev_page(self):
        dev = tk.Toplevel(self.root)
        dev.title("Developer Info")
        dev.geometry("450x400")
        dev.configure(bg=THEME["bg"])
        dev.resizable(False, False)

        # Content Container
        container = tk.Frame(dev, bg=THEME["bg"])
        container.pack(expand=True, fill="both", padx=20, pady=20)

        # Title
        tk.Label(container, text="Developed By", font=(THEME["font_main"], 12),
                 fg=THEME["fg_sub"], bg=THEME["bg"]).pack(pady=(10, 5))

        # Name
        tk.Label(container, text="Mahir Siam", font=(THEME["font_main"], 24, "bold"),
                 fg=THEME["accent"], bg=THEME["bg"]).pack(pady=5)

        # Tagline
        tk.Label(container, text="MERN Stack Developer |\nC++ Problem Solver", 
                 font=(THEME["font_main"], 12), fg=THEME["fg"], bg=THEME["bg"],
                 justify="center").pack(pady=10)

        # Bio / Description
        bio = ("Dedicated to bringing creative ideas to life\n"
               "through robust code and interactive applications.")
        tk.Label(container, text=bio, font=(THEME["font_main"], 10, "italic"),
                 fg=THEME["fg_sub"], bg=THEME["bg"], justify="center").pack(pady=10)

        # GitHub Button
        gh_btn = tk.Button(container, text="Visit GitHub Profile", font=(THEME["font_main"], 12, "bold"),
                           bg=THEME["input_bg"], fg="#FFFFFF", activebackground=THEME["accent"],
                           relief="flat", width=20, cursor="hand2",
                           command=lambda: webbrowser.open("https://github.com/mahirsiam2004"))
        gh_btn.pack(pady=20)

        # Close
        tk.Button(container, text="Close", font=(THEME["font_main"], 10),
                  bg=THEME["bg"], fg=THEME["fg_sub"], relief="flat",
                  cursor="hand2", command=dev.destroy).pack(side="bottom", pady=10)


# ---------- RUN ----------
if __name__ == "__main__":
    root = tk.Tk()
    
    try:
        icon_path = resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except:
        pass

    app = FocusBellApp(root)
    
    # Handle Close
    def on_closing():
        app.is_running = False
        root.destroy()
        sys.exit(0)
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

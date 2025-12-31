import os
import time
import threading
import numpy as np
import tkinter as tk
from tkinter import ttk
import scservo_sdk as scs

# =========================
# CONFIG (확정)
# =========================
LEADER_PORT   = "COM6"
FOLLOWER_PORT = "COM7"

BAUD = 1_000_000
PROTOCOL = 1

JOINT_IDS = [1, 2, 3, 4, 5, 6]
NUM_JOINTS = 6

ADDR_PRESENT_POSITION = 56
ADDR_GOAL_POSITION    = 42

DT = 0.02  # 50Hz

# =========================
# RECORD DIR
# =========================
RECORD_DIR = "records"
os.makedirs(RECORD_DIR, exist_ok=True)

def next_path():
    files = sorted(
        f for f in os.listdir(RECORD_DIR)
        if f.startswith("raw_") and f.endswith(".npy")
    )
    idx = int(files[-1][4:7]) + 1 if files else 0
    return os.path.join(RECORD_DIR, f"raw_{idx:03d}.npy")

# =========================
# SDK INIT
# =========================
leader_port = scs.PortHandler(LEADER_PORT)
follower_port = scs.PortHandler(FOLLOWER_PORT)
packet = scs.PacketHandler(PROTOCOL)

leader_port.openPort()
follower_port.openPort()
leader_port.setBaudRate(BAUD)
follower_port.setBaudRate(BAUD)

# PortHandler()  →  "이 COM 포트를 다룰 객체를 만든다"
# openPort()    →  "운영체제에게 실제로 이 포트를 열어달라고 요청한다"
# setBaudRate() →  "통신 속도를 서보 설정과 일치시킨다"

print("[INIT] ports opened")

# =========================
# IO
# =========================
def read_leader():
    q = np.zeros(NUM_JOINTS, dtype=np.int32)
    for i, dxl_id in enumerate(JOINT_IDS):
        pos, _, _ = packet.read2ByteTxRx(
            leader_port, dxl_id, ADDR_PRESENT_POSITION
        )
        q[i] = int(pos)
    return q

def write_follower(q):
    for dxl_id, v in zip(JOINT_IDS, q):
        packet.write2ByteTxRx(
            follower_port, dxl_id, ADDR_GOAL_POSITION, int(v)
        )

# =========================
# STATE
# =========================
running   = True
mode      = "TELEOP"   # TELEOP / RECORD / REPLAY
recording = False

buffer     = [] 
save_path  = None
last_saved = None

# =========================
# ROBOT LOOP (키보드 코드와 동일한 역할)
# =========================
def robot_loop():
    global running, mode, recording, buffer

    while running:
        # REPLAY 중에는 완전히 정지 (키보드 코드와 동일 효과)
        if mode == "REPLAY":
            time.sleep(DT)
            continue

        q_leader = read_leader()
        write_follower(q_leader)

        if recording:
            buffer.append(q_leader.copy())

        time.sleep(DT)

# =========================
# GUI CALLBACKS
# =========================
def log(msg):
    log_box.insert(tk.END, msg + "\n")
    log_box.see(tk.END)

def start_record():
    global recording, buffer, save_path, mode

    if recording:
        return

    mode = "RECORD"
    recording = True
    buffer = []
    save_path = next_path()

    status_var.set("● RECORDING")
    log(f"[RECORD] START → {os.path.basename(save_path)}")

def stop_record():
    global recording, buffer, last_saved, mode

    if not recording:
        return

    recording = False
    mode = "TELEOP"
    status_var.set("IDLE")

    if buffer:
        np.save(save_path, np.array(buffer, dtype=np.int32))
        last_saved = save_path
        log(f"[RECORD] SAVED ({len(buffer)} frames)")
    else:
        log("[RECORD] STOP (no frames)")

    buffer = []

def replay():
    global mode, last_saved

    if recording:
        log("[WARN] stop record before replay")
        return

    if last_saved is None or not os.path.exists(last_saved):
        files = sorted(
            os.path.join(RECORD_DIR, f)
            for f in os.listdir(RECORD_DIR)
            if f.startswith("raw_")
        )
        if not files:
            log("[REPLAY] no recordings")
            return
        last_saved = files[-1]

    seq = np.load(last_saved)

    mode = "REPLAY"
    status_var.set("▶ REPLAY")
    log(f"[REPLAY] {os.path.basename(last_saved)} ({len(seq)} frames)")

    for q in seq:
        write_follower(q)
        time.sleep(DT)

    mode = "TELEOP"
    status_var.set("IDLE")
    log("[REPLAY] DONE")

def quit_all():
    global running
    running = False
    time.sleep(0.05)

    leader_port.closePort()
    follower_port.closePort()

    root.destroy()
    print("[DONE]")

# =========================
# GUI (DESIGN UPGRADE)
# =========================
root = tk.Tk()
root.title("Leader–Follower Recorder v1.0")
root.geometry("460x520")
root.configure(bg="#1e1e1e")  # 다크 배경

style = ttk.Style()
style.theme_use("default")

style.configure("TButton",
    font=("Consolas", 11),
    padding=8
)

style.configure("Record.TButton",
    background="#c0392b",
    foreground="white"
)

style.configure("Stop.TButton",
    background="#7f8c8d",
    foreground="white"
)

style.configure("Replay.TButton",
    background="#2980b9",
    foreground="white"
)

style.configure("Quit.TButton",
    background="#2c3e50",
    foreground="white"
)

style.configure("Status.TLabel",
    background="#111111",
    foreground="#00ff99",
    font=("Consolas", 14),
    padding=10,
    relief="solid"
)

# ---- Title ----
tk.Label(
    root,
    text="LEADER – FOLLOWER CONTROL",
    font=("Consolas", 14, "bold"),
    bg="#1e1e1e",
    fg="#ffffff"
).pack(pady=12)

# ---- Status ----
status_var = tk.StringVar(value="IDLE")
status_label = ttk.Label(
    root,
    textvariable=status_var,
    style="Status.TLabel"
)
status_label.pack(fill="x", padx=20, pady=10)

# ---- Buttons ----
btn_frame = tk.Frame(root, bg="#1e1e1e")
btn_frame.pack(fill="x", padx=20)

ttk.Button(
    btn_frame,
    text="▶ START RECORD",
    command=start_record,
    style="Record.TButton"
).pack(fill="x", pady=5)

ttk.Button(
    btn_frame,
    text="■ STOP RECORD",
    command=stop_record,
    style="Stop.TButton"
).pack(fill="x", pady=5)

ttk.Button(
    btn_frame,
    text="⏯ REPLAY",
    command=replay,
    style="Replay.TButton"
).pack(fill="x", pady=5)

ttk.Button(
    btn_frame,
    text="✖ QUIT",
    command=quit_all,
    style="Quit.TButton"
).pack(fill="x", pady=10)

# ---- Log ----
tk.Label(
    root,
    text="SYSTEM LOG",
    font=("Consolas", 11),
    bg="#1e1e1e",
    fg="#aaaaaa"
).pack(pady=(10, 0))

log_box = tk.Text(
    root,
    height=10,
    bg="#0d0d0d",
    fg="#00ff99",
    insertbackground="white",
    font=("Consolas", 10),
    relief="solid",
    borderwidth=1
)
log_box.pack(fill="both", expand=True, padx=20, pady=10)


# =========================
# THREAD START
# =========================
threading.Thread(target=robot_loop, daemon=True).start()
root.protocol("WM_DELETE_WINDOW", quit_all)

root.mainloop()

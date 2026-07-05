import serial
import os
import time
import matplotlib
matplotlib.use("TkAgg")   # Use "Qt5Agg" instead if PyQt5 is available
import matplotlib.pyplot as plt
import csv
from datetime import datetime
from serial import Serial
import threading
import tkinter as tk
from tkinter import messagebox
from matplotlib.animation import FuncAnimation
import signal
import sys



#-----------------------*-----------------------
# 001 --> address
# 0 --> read command
# 740 --> pressure measurement
# 02 --> data length
# =? --> request to read this parameter
# 106 --> checksum

# MPT200 returns something like: 0011074006100023025
# 001 --> address
# 1 --> reply command
# 740 --> pressure measurement
# 06 --> data length
# 100023 --> pressure data
# 106 --> checksum
#-------------*-----------------------

# Variables
# Main flag used to stop the acquisition
running = True

# Data buffers used for live plotting
check="00310740"  # Keep only Pfeiffer frames starting with this header (pressure measurement; see MPT200 manual)
pressure_mpt200_list = []
t_mpt200 = []

temp_ard_list = []
t_ard = []

temp_pt100_list = []
temp_bath_list = []
t_bath = []



# Reference time for elapsed-time plots
start = time.time()

# Serial port settings
mpt200_port = "/dev/ttyUSB4"                # Serial port
CMD = b"0010074002=?106\r"                  # Pfeiffer command to read pressure


serial_port_arduino = '/dev/ttyUSB2'
baud_rate_arduino = 9600

serial_port_temp = '/dev/ttyUSB3'
baud_rate_temp = 4800

# Timestamp used in the output filename
t_csv = datetime.now().isoformat(timespec='minutes').replace('T','-')
# Create the CSV file and write the header
base_dir = "/home/antonio/SSD_up/Iago/vacuum_setup"
os.makedirs(base_dir, exist_ok=True)

file = os.path.join(base_dir, f"meas_vac_setup{t_csv}.csv")
csv_lock = threading.Lock()
with open(file, 'a', newline='') as f:
    w = csv.writer(f)
    with csv_lock:
        w.writerow(["Time", "pressure_mpt200", "T (arduino)", "T (bath)"])
        f.flush()

# =========================
# Four-column CSV: time plus three values, using carry-forward
# =========================
last_pressure_mpt200 = ""
last_temp_arduino   = ""
last_bath_temp      = ""

def log_csv_row(w, f, t_now, pressure=None, temp_arduino=None, bath_temp=None):
    """
    Always write four columns: [time, pressure_mpt200, temp_arduino, bath_temp].
    If a value is not updated at this step, keep the last known value.
    """
    global last_pressure_mpt200, last_temp_arduino, last_bath_temp
    with csv_lock:
        if pressure is not None:
            last_pressure_mpt200 = pressure
        if temp_arduino is not None:
            last_temp_arduino = temp_arduino
        if bath_temp is not None:
            last_bath_temp = bath_temp

        w.writerow([f"{t_now}", last_pressure_mpt200, last_temp_arduino, last_bath_temp])
        f.flush()
# =========================


def parse_mpt200_pressure(reply: str):
    if not reply.isdigit():
        return None
    if not reply.startswith(check):   # Use the exact header expected here: "00310740"
        return None
    if len(reply) < 12:  # Basic sanity check
        return None

    # Six data digits placed just before the three-digit checksum
    data6 = reply[-9:-3]
    if len(data6) != 6 or not data6.isdigit():
        return None

    mant = int(data6[:4])
    expo = int(data6[4:6])
    pressure = (mant / 1000.0) * (10 ** (expo - 20))
    return pressure



def read_mpt200_serial():
    print("Reading MPT200... (q/Esc o cerrar ventana para parar)")
    try:
        ser.reset_input_buffer()  # Drop any junk already in the input buffer

        with open(file, 'a', newline='') as f:
            w = csv.writer(f)

            # Used to avoid flushing to disk on every sample
            last_flush_t = time.time()

            while running:
                # If the MPT200 does not stream continuously and needs polling,
                # uncomment these two lines:
                # ser.write(CMD)
                # ser.flush()

                # 1) Read one frame; it may be an old one
                raw = ser.read_until(b"\r")  # uses the Serial timeout set above

                # 2) Drain the buffer and keep only the latest complete frame
                while ser.in_waiting > 0:
                    raw = ser.read_until(b"\r")

                reply = raw.decode(errors="ignore").strip()
                pressure_mpt200 = parse_mpt200_pressure(reply)
                if pressure_mpt200 is None:
                    continue


                t_now = datetime.now().isoformat(timespec='seconds').replace('T','-')
                print(f"Time: {t_now}, Pressure: {pressure_mpt200:.3e} mbar\n")

                # CSV logging; flush roughly once per second
                log_csv_row(w, f, t_now, pressure=pressure_mpt200)
                if time.time() - last_flush_t > 1.0:
                    f.flush()
                    last_flush_t = time.time()

                # Store data for plotting
                t_mpt200.append(time.time() - start)
                pressure_mpt200_list.append(pressure_mpt200)

                # Keep this delay short if you want to throttle the loop
                # With the latest-only readout, old frames are not replayed
                time.sleep(0.05)

    except Exception as e:
        print("MPT200 thread error:", e)
    finally:
        try:
            ser.close()
        except Exception:
            pass



# Read Arduino data and log/display it
def read_arduino_serial():
    with open(file, 'a', newline='') as f:
        w = csv.writer(f)

        try:
            while running:
                if ser_arduino.in_waiting > 0:
                    line = ser_arduino.readline().decode('utf-8').strip()
                    if "Avg Temperature" in line:
                        try:
                            temp_ard_str = line.split("Avg Temperature : ")[1].split(',')[0].strip()
                            temp_ard = float(temp_ard_str[0:4])
                            temp_ard_list.append(temp_ard)
                            t_ard.append(time.time()-start)
                            print("T (Arduino)", temp_ard)

                            t_now = datetime.now().isoformat(timespec='seconds').replace('T','-')
                            # Four-column CSV row
                            log_csv_row(w, f, t_now, temp_arduino=temp_ard)

                        except Exception:
                            continue
        except Exception as e:
            print(f"Error: {e}")
        finally:
            ser_arduino.close()
            print("Arduino serial connection closed.")

# Request bath temperature data and log/display it
def read_temp_serial():
    with open(file, 'a', newline='') as f:
        w = csv.writer(f)
        try:
            while running:
                
                # Request bath temperature
                ser_temp.write(b"IN_PV_00\r\n")
                time.sleep(0.5)
                if ser_temp.in_waiting > 0:
                    bath_temp = ser_temp.readline().decode('utf-8').strip()
                    print(f"Bath: {bath_temp}")

                    t_now = datetime.now().isoformat(timespec='seconds').replace('T','-')
                    # Four-column CSV row
                    log_csv_row(w, f, t_now, bath_temp=bath_temp)

                try:

                    bath_temp = float(bath_temp)
                    temp_bath_list.append(bath_temp)
                    t_bath.append(time.time()-start)
                except Exception as e:
                        continue
                

                time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            ser_temp.close()
            print("Temperature serial connection closed.")


# Update the live plots
def update_plot(frame):
    # Fast copies, so plotting is not affected if threads append data
    t_p = list(t_mpt200)
    p   = list(pressure_mpt200_list)

    t_a = list(t_ard)
    Ta  = list(temp_ard_list)

    t_b = list(t_bath)
    Tb  = list(temp_bath_list)

    # Clear the current axes (global ax1, ax2, ax3)
    ax1.cla()
    ax2.cla()
    ax3.cla()

    # --- MPT200 pressure ---
    if t_p and p:
        ax1.plot(t_p, p, label='MPT200 Pressure')
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('Pressure (mbar)')
        ax1.set_yscale("log")  # Useful under vacuum; remove it if a linear scale is preferred
        ax1.legend(loc='upper right')

    # --- Arduino temperature ---
    if t_a and Ta:
        ax2.plot(t_a, Ta, label='Arduino Temperature (C)')
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel('PT100 Temperature (ºC)')
        ax2.legend(loc='upper right')

    # --- Bath temperature ---
    if t_b and Tb:
        ax3.plot(t_b, Tb, label='Bath Temperature (C)')
        ax3.set_xlabel('Time (s)')
        ax3.set_ylabel('Bath Temperature (ºC)')
        ax3.legend(loc='upper right')

    fig.tight_layout()


# Open serial connections
ser = serial.Serial(mpt200_port, 9600, timeout=1)

ser_arduino = serial.Serial(serial_port_arduino, baud_rate_arduino)

ser_temp = serial.Serial(
    serial_port_temp,
    baud_rate_temp,
    bytesize=serial.SEVENBITS,
    parity=serial.PARITY_EVEN,
    stopbits=serial.STOPBITS_ONE,
    rtscts=True
)

# Start one acquisition thread per serial device
thread_arduino = threading.Thread(target=read_arduino_serial)
thread_temp = threading.Thread(target=read_temp_serial)
thread_mpt200 = threading.Thread(target=read_mpt200_serial)
thread_arduino.start()
thread_temp.start()
thread_mpt200.start()


# Set up the live plot
fig, (ax1, ax2, ax3) = plt.subplots(3, 1)

ani = FuncAnimation(fig, update_plot, interval=1000)


# =========================
# Simple shutdown: close window, q/Esc key, or Ctrl+C if caught
# =========================
def request_stop(*_):
    global running
    if not running:
        return
    running = False

    # Stop the animation if it exists
    try:
        ani.event_source.stop()
    except Exception:
        pass

    # Close serial ports to unblock the worker threads
    for name in ("ser", "ser_arduino", "ser_temp"):
        s = globals().get(name)
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

    # Close all figures so plt.show() returns
    try:
        plt.close('all')
    except Exception:
        pass

# Closing the window stops the acquisition
fig.canvas.mpl_connect('close_event', request_stop)

# Key presses inside the figure stop the acquisition
def on_key(event):
    if event.key in ('q', 'escape'):
        request_stop()
fig.canvas.mpl_connect('key_press_event', on_key)

# Ctrl+C in the terminal also requests shutdown, when the signal is caught
signal.signal(signal.SIGINT, lambda sig, frame: request_stop())
# =========================



try:
    plt.show()

except KeyboardInterrupt:
    print("Programm interrupted!")
    print("Saving CSV to:", file)
    request_stop()

finally:
    request_stop()
    for th in (thread_arduino, thread_temp, thread_mpt200):
        try:
            th.join(timeout=2)
        except Exception:
            pass

    print("Saving CSV to:", file)
    os._exit(0)

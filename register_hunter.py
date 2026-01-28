import socket
import struct
import time
import sys

# --- CONFIG ---
TARGET_IP = "127.0.0.1" 
TARGET_PORT = 9999      
TIMEOUT = 5
CHUNK_SIZE = 10  # Reduced from 50 to 10 to prevent timeouts

def get_modbus_block(start_reg, count):
    hex_cmd = f"0103{start_reg:04x}{count:04x}"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((TARGET_IP, TARGET_PORT))
        s.send(f"RAW:{hex_cmd}".encode())
        response = s.recv(4096).strip()
        s.close()
        
        if b"ERROR" in response or b"TIMEOUT" in response or len(response) == 0:
            return None
        
        try:
            data_bytes = bytes.fromhex(response.decode())
        except:
            return None

        # Check length: [Addr][Func][ByteCount][Data...][CRC]
        if len(data_bytes) < 5 + (count * 2): return None
        payload = data_bytes[3:-2] 
        
        values = []
        for i in range(0, len(payload), 2):
            val = struct.unpack('>H', payload[i:i+2])[0]
            values.append(val)
        return values
    except Exception as e:
        return None

def scan_all_registers():
    print(f"Reading Registers 0-600 in chunks of {CHUNK_SIZE}...")
    memory_map = {}
    
    for start in range(0, 600, CHUNK_SIZE):
        vals = get_modbus_block(start, CHUNK_SIZE)
        if vals:
            for i, val in enumerate(vals):
                memory_map[start + i] = val
            sys.stdout.write("#") # Success
        else:
            sys.stdout.write(".") # Failure
        sys.stdout.flush()
        time.sleep(0.1) 
    print("\nScan complete.")
    return memory_map

if __name__ == "__main__":
    print("--- STEP 1: CAPTURE BASELINE ---")
    print("Set Inverter to MODE A (e.g., UTI).")
root@dnsmasq:~# cat register_hunter.py
import socket
import struct
import time

# --- CONFIGURATION ---
BIND_IP = '0.0.0.0'
PORT = 18899

# Range to scan
START_REG = 0
END_REG = 600 

def modbus_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for i in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc)

def build_read_packet(start, count):
    payload = struct.pack('>BBHH', 1, 3, start, count)
    return payload + modbus_crc(payload)

def read_block(conn, start, end):
    values = {}
    chunk_size = 50 
    
    print(f"   Reading registers {start} to {end}...", end="", flush=True)
    for i in range(start, end, chunk_size):
        try:
            conn.send(build_read_packet(i, chunk_size))
            time.sleep(0.1) 
            raw = conn.recv(1024)
            if len(raw) > 5:
                byte_count = raw[2]
                data = raw[3 : 3 + byte_count]
                chunk_vals = [x[0] for x in struct.iter_unpack('>H', data)]
                for idx, val in enumerate(chunk_vals):
                    values[i + idx] = val
            print(".", end="", flush=True)
        except: pass
    print(" Done.")
    return values

def main():
    print(f"[*] Waiting for Inverter on port {PORT}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((BIND_IP, PORT))
    s.listen(1)
    
    # Wait for the DNAT/Hijack connection
    conn, addr = s.accept()
    print(f"[+] Connected by: {addr} (likely Router IP)")
    conn.settimeout(5.0)

    # --- PHASE 1: SNAPSHOT ---
    print("\n--- PHASE 1: INITIAL SNAPSHOT ---")
    baseline = read_block(conn, START_REG, END_REG)
    print(f"Captured {len(baseline)} registers.")
    
    print("\n" + "="*50)
    print("ACTION REQUIRED:")
    print("1. Go to the Inverter LCD Screen.")
    print("2. Change ONE setting (e.g., Battery Type or Buzzer).")
    print("3. Wait 5 seconds for the inverter to save it.")
    print("4. Come back here and press ENTER.")
    print("="*50)
    input()
    
    # --- PHASE 2: COMPARISON ---
    print("\n--- PHASE 2: COMPARISON SCAN ---")
    new_state = read_block(conn, START_REG, END_REG)
    
    print("\n" + "="*50)
    print("RESULTS - The following registers changed:")
    print("="*50)
    
    found_any = False
    for reg in sorted(baseline.keys()):
        val_old = baseline.get(reg)
        val_new = new_state.get(reg)
        
        if val_new is not None and val_old != val_new:
            print(f"🎯 Register {reg}:  Was {val_old}  ->  Now {val_new}")
            found_any = True
            
    if not found_any:
        print("No changes detected.")
    
    conn.close()
    s.close()

if __name__ == "__main__":
    main()

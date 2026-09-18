"""
Modern Automated Parking Management System
Data Structures and Algorithms - Task One

This is a console implementation of the parking-system
design document. It uses:
- Lists for parking slots
- A dictionary (hash table) for fast active-vehicle lookup
- deque as a FIFO waiting queue
- SQLite for a dynamic persistent database

The system can:
1. Display parking availability
2. Register/enter a vehicle
3. Allocate a parking slot
4. Record entry time
5. Process vehicle exit
6. Calculate parking duration
7. Calculate parking fee
8. Record payment
9. Release the parking slot
10. Display parking status and transaction history
"""

import sqlite3
import math
from datetime import datetime
from collections import deque
import os

# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = "parking_system.db"

# Illustrative tariff from the design document:
# First hour = KSh 50
# Every additional hour or part thereof = KSh 30
FIRST_HOUR_RATE = 50
ADDITIONAL_HOUR_RATE = 30


# ============================================================
# DATABASE
# ============================================================

def connect_database():
    """Connect to the SQLite database."""
    return sqlite3.connect(DATABASE_NAME)


def create_tables():
    """Create the database tables if they do not already exist."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_no TEXT NOT NULL UNIQUE,
            vehicle_type TEXT NOT NULL,
            owner_name TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_slots (
            slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_number TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'AVAILABLE',
            location TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            slot_id INTEGER NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            duration_minutes INTEGER,
            fee REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
            FOREIGN KEY (slot_id) REFERENCES parking_slots(slot_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_time TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES parking_sessions(session_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def create_default_slots(number_of_slots=10):
    """
    Create parking slots only when the database has no slots.
    Example: A01, A02, ..., A10.
    """
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM parking_slots")
    count = cursor.fetchone()[0]

    if count == 0:
        for i in range(1, number_of_slots + 1):
            slot_number = f"A{i:02d}"
            cursor.execute("""
                INSERT INTO parking_slots (slot_number, status, location)
                VALUES (?, 'AVAILABLE', 'Ground Floor')
            """, (slot_number,))

    conn.commit()
    conn.close()


# ============================================================
# PARKING AVAILABILITY MODULE
# ============================================================

def get_parking_slots():
    """Return all parking slots as a list."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT slot_id, slot_number, status, location
        FROM parking_slots
        ORDER BY slot_id
    """)

    slots = cursor.fetchall()
    conn.close()

    return slots


def display_availability():
    """
    Display the number of available and occupied parking spaces.
    Uses a list to hold the slot records.
    """
    slots = get_parking_slots()

    available_slots = []
    occupied_slots = []

    for slot in slots:
        slot_id, slot_number, status, location = slot

        if status == "AVAILABLE":
            available_slots.append(slot_number)
        else:
            occupied_slots.append(slot_number)

    print("\n========== PARKING AVAILABILITY ==========")
    print(f"Total slots    : {len(slots)}")
    print(f"Available      : {len(available_slots)}")
    print(f"Occupied       : {len(occupied_slots)}")

    if available_slots:
        print("Available slots:", ", ".join(available_slots))
    else:
        print("PARKING FULL")

    print("==========================================\n")


# ============================================================
# SLOT ALLOCATION MODULE
# ============================================================

def find_available_slot():
    """
    Find the first available parking slot.

    Sequential search through a list is O(n).
    """
    slots = get_parking_slots()

    for slot in slots:
        slot_id, slot_number, status, location = slot

        if status == "AVAILABLE":
            return slot_id, slot_number

    return None


def occupy_slot(slot_id):
    """Change a slot from AVAILABLE to OCCUPIED."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE parking_slots
        SET status = 'OCCUPIED'
        WHERE slot_id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()


def release_slot(slot_id):
    """Change a slot from OCCUPIED to AVAILABLE."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE parking_slots
        SET status = 'AVAILABLE'
        WHERE slot_id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()


# ============================================================
# VEHICLE REGISTRATION MODULE
# ============================================================

def get_or_create_vehicle(registration_no, vehicle_type, owner_name):
    """
    Find a vehicle by registration number.
    If it does not exist, create it.
    """
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT vehicle_id
        FROM vehicles
        WHERE registration_no = ?
    """, (registration_no,))

    existing = cursor.fetchone()

    if existing:
        vehicle_id = existing[0]
        conn.close()
        return vehicle_id

    cursor.execute("""
        INSERT INTO vehicles (registration_no, vehicle_type, owner_name)
        VALUES (?, ?, ?)
    """, (registration_no, vehicle_type, owner_name))

    vehicle_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return vehicle_id


# ============================================================
# ACTIVE VEHICLE HASH TABLE / DICTIONARY
# ============================================================

def load_active_vehicle_dictionary():
    """
    Build an in-memory dictionary:
        registration number -> session details

    This demonstrates the hash-table data structure.
    Average lookup is approximately O(1).
    """
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            v.registration_no,
            ps.session_id,
            ps.slot_id,
            ps.entry_time
        FROM parking_sessions ps
        JOIN vehicles v ON ps.vehicle_id = v.vehicle_id
        WHERE ps.status = 'ACTIVE'
    """)

    records = cursor.fetchall()
    conn.close()

    active_vehicles = {}

    for registration_no, session_id, slot_id, entry_time in records:
        active_vehicles[registration_no] = {
            "session_id": session_id,
            "slot_id": slot_id,
            "entry_time": entry_time
        }

    return active_vehicles


# ============================================================
# VEHICLE ENTRY MODULE
# ============================================================

def vehicle_entry():
    """Register a vehicle and admit it into the parking facility."""
    print("\n========== VEHICLE ENTRY ==========")

    display_availability()

    slot = find_available_slot()

    if slot is None:
        print("No parking slot is available.")
        print("Entry barrier remains CLOSED.")
        return

    registration_no = input("Enter vehicle registration number: ").strip().upper()

    if not registration_no:
        print("Registration number cannot be empty.")
        return

    # Hash-table lookup
    active_vehicles = load_active_vehicle_dictionary()

    if registration_no in active_vehicles:
        print("This vehicle already has an active parking session.")
        print("Entry barrier remains CLOSED.")
        return

    vehicle_type = input(
        "Enter vehicle type (Car/Motorcycle/Van/etc.): "
    ).strip()

    if not vehicle_type:
        vehicle_type = "Car"

    owner_name = input("Enter owner/driver name (optional): ").strip()

    vehicle_id = get_or_create_vehicle(
        registration_no,
        vehicle_type,
        owner_name
    )

    slot_id, slot_number = slot

    entry_time = datetime.now()

    conn = connect_database()
    cursor = conn.cursor()

    # Create parking session
    cursor.execute("""
        INSERT INTO parking_sessions
        (vehicle_id, slot_id, entry_time, status)
        VALUES (?, ?, ?, 'ACTIVE')
    """, (
        vehicle_id,
        slot_id,
        entry_time.strftime("%Y-%m-%d %H:%M:%S")
    ))

    session_id = cursor.lastrowid

    # Mark slot occupied
    cursor.execute("""
        UPDATE parking_slots
        SET status = 'OCCUPIED'
        WHERE slot_id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    print("\nVehicle successfully registered.")
    print(f"Registration : {registration_no}")
    print(f"Parking slot : {slot_number}")
    print(f"Entry time   : {entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("Entry barrier: OPEN")
    print("Please proceed to the assigned parking slot.")
    print("===================================\n")


# ============================================================
# PARKING DURATION MODULE
# ============================================================

def calculate_duration(entry_time, exit_time):
    """
    Calculate parking duration in minutes.

    Time subtraction is O(1).
    """
    duration = exit_time - entry_time
    return int(duration.total_seconds() // 60)


# ============================================================
# FEE CALCULATION MODULE
# ============================================================

def calculate_fee(duration_minutes):
    """
    Calculate parking fee using the illustrative tariff.

    First hour: KSh 50
    Each additional hour or part thereof: KSh 30
    """
    if duration_minutes <= 60:
        return FIRST_HOUR_RATE

    additional_minutes = duration_minutes - 60
    additional_hours = math.ceil(additional_minutes / 60)

    return FIRST_HOUR_RATE + (
        additional_hours * ADDITIONAL_HOUR_RATE
    )


# ============================================================
# PAYMENT MODULE
# ============================================================

def record_payment(session_id, amount, payment_method):
    """Record a successful payment in the database."""
    conn = connect_database()
    cursor = conn.cursor()

    payment_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO payments
        (session_id, amount, payment_method, payment_time, payment_status)
        VALUES (?, ?, ?, ?, 'SUCCESSFUL')
    """, (
        session_id,
        amount,
        payment_method,
        payment_time
    ))

    conn.commit()
    conn.close()


# ============================================================
# VEHICLE EXIT MODULE
# ============================================================

def vehicle_exit():
    """Calculate the bill, process payment and release the vehicle."""
    print("\n========== VEHICLE EXIT ==========")

    registration_no = input(
        "Enter vehicle registration number: "
    ).strip().upper()

    if not registration_no:
        print("Registration number cannot be empty.")
        return

    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ps.session_id,
            ps.slot_id,
            ps.entry_time,
            pslot.slot_number
        FROM parking_sessions ps
        JOIN vehicles v
            ON ps.vehicle_id = v.vehicle_id
        JOIN parking_slots pslot
            ON ps.slot_id = pslot.slot_id
        WHERE v.registration_no = ?
          AND ps.status = 'ACTIVE'
    """, (registration_no,))

    record = cursor.fetchone()
    conn.close()

    if record is None:
        print("Vehicle record not found.")
        print("Exit barrier remains CLOSED.")
        return

    session_id, slot_id, entry_time_text, slot_number = record

    entry_time = datetime.strptime(
        entry_time_text,
        "%Y-%m-%d %H:%M:%S"
    )

    exit_time = datetime.now()

    duration_minutes = calculate_duration(
        entry_time,
        exit_time
    )

    fee = calculate_fee(duration_minutes)

    hours = duration_minutes // 60
    minutes = duration_minutes % 60

    print("\n========== PARKING BILL ==========")
    print(f"Registration : {registration_no}")
    print(f"Parking slot : {slot_number}")
    print(f"Entry time   : {entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Exit time    : {exit_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration     : {hours} hour(s), {minutes} minute(s)")
    print(f"Amount due   : KSh {fee:.2f}")
    print("==================================")

    payment_method = input(
        "Payment method (Cash/M-Pesa/Card): "
    ).strip()

    if not payment_method:
        print("Payment method is required.")
        print("Exit barrier remains CLOSED.")
        return

    # Simple classroom simulation of payment.
    # In a real system this would connect to a payment provider.
    payment_confirmation = input(
        "Confirm payment was successful? (yes/no): "
    ).strip().lower()

    if payment_confirmation != "yes":
        print("Payment was not confirmed.")
        print("Exit barrier remains CLOSED.")
        return

    # Update session
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE parking_sessions
        SET exit_time = ?,
            duration_minutes = ?,
            fee = ?,
            status = 'COMPLETED'
        WHERE session_id = ?
    """, (
        exit_time.strftime("%Y-%m-%d %H:%M:%S"),
        duration_minutes,
        fee,
        session_id
    ))

    # Release slot
    cursor.execute("""
        UPDATE parking_slots
        SET status = 'AVAILABLE'
        WHERE slot_id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    # Record payment after the session update
    record_payment(
        session_id,
        fee,
        payment_method
    )

    print("\nPayment successful.")
    print(f"Amount paid: KSh {fee:.2f}")
    print(f"Slot {slot_number} is now AVAILABLE.")
    print("Exit barrier: OPEN")
    print("Thank you. Drive safely!")
    print("==================================\n")


# ============================================================
# PARKING STATUS MODULE
# ============================================================

def display_detailed_status():
    """Display every parking slot and its current status."""
    slots = get_parking_slots()

    print("\n========== PARKING SLOT STATUS ==========")

    for slot in slots:
        slot_id, slot_number, status, location = slot
        print(
            f"{slot_number:<6} | "
            f"{status:<10} | "
            f"{location}"
        )

    print("=========================================\n")


# ============================================================
# TRANSACTION HISTORY
# ============================================================

def display_history():
    """Display completed parking sessions."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            v.registration_no,
            ps.entry_time,
            ps.exit_time,
            ps.duration_minutes,
            ps.fee,
            ps.status
        FROM parking_sessions ps
        JOIN vehicles v
            ON ps.vehicle_id = v.vehicle_id
        ORDER BY ps.session_id DESC
    """)

    records = cursor.fetchall()
    conn.close()

    print("\n========== PARKING HISTORY ==========")

    if not records:
        print("No parking records found.")
    else:
        for record in records:
            registration_no, entry_time, exit_time, duration, fee, status = record

            print(f"Vehicle   : {registration_no}")
            print(f"Entry     : {entry_time}")
            print(f"Exit      : {exit_time if exit_time else 'Still parked'}")
            print(f"Duration  : {duration if duration is not None else '-'} minutes")
            print(f"Fee       : KSh {fee:.2f}")
            print(f"Status    : {status}")
            print("-" * 35)

    print("=====================================\n")


# ============================================================
# WAITING QUEUE
# ============================================================

waiting_queue = deque()


def add_to_waiting_queue():
    """Add a vehicle registration number to the FIFO waiting queue."""
    registration_no = input(
        "Enter registration number to add to waiting queue: "
    ).strip().upper()

    if registration_no:
        waiting_queue.append(registration_no)
        print(
            f"{registration_no} added to the waiting queue."
        )
    else:
        print("Registration number cannot be empty.")


def show_waiting_queue():
    """Display the FIFO waiting queue."""
    print("\n========== WAITING QUEUE ==========")

    if not waiting_queue:
        print("No vehicles are waiting.")
    else:
        for position, registration_no in enumerate(
            waiting_queue,
            start=1
        ):
            print(
                f"{position}. {registration_no}"
            )

    print("===================================\n")

# ============================================================
# WEB BACKEND API
# ============================================================
# The website will communicate with this Python backend.
# Install Flask once with:
#     pip install flask
#
# Then run this file and open:
#     http://127.0.0.1:5000
# ============================================================

from flask import Flask, request,jsonify
from flask_cors import CORS

app = Flask(__name__,static_folder="../website",static_url_path="")
@app.route("/")
def home():
    return app.send_static_file("index.html")
CORS(app)


@app.route("/api/parking", methods=["GET"])
def api_parking():
    """Return the current status of every parking slot."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT slot_id, slot_number, status, location
        FROM parking_slots
        ORDER BY slot_id
    """)

    rows = cursor.fetchall()
    conn.close()

    slots = [
        {
            "slot_id": row[0],
            "slot_number": row[1],
            "status": row[2],
            "location": row[3],
        }
        for row in rows
    ]

    available = sum(1 for slot in slots if slot["status"] == "AVAILABLE")

    return jsonify({
        "total_slots": len(slots),
        "available_slots": available,
        "occupied_slots": len(slots) - available,
        "slots": slots,
    })


@app.route("/api/entry", methods=["POST"])
def api_entry():
    """Register a vehicle and assign an available parking slot."""
    data = request.get_json(silent=True) or {}
    registration_no = str(data.get("registration_no", "")).strip().upper()
    vehicle_type = str(data.get("vehicle_type", "Car")).strip() or "Car"
    owner_name = str(data.get("owner_name", "")).strip()

    if not registration_no:
        return jsonify({"success": False, "message": "Registration number is required."}), 400

    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT vehicle_id
        FROM vehicles
        WHERE registration_no = ?
    """, (registration_no,))
    vehicle = cursor.fetchone()

    if vehicle:
        vehicle_id = vehicle[0]
    else:
        cursor.execute("""
            INSERT INTO vehicles (registration_no, vehicle_type, owner_name)
            VALUES (?, ?, ?)
        """, (registration_no, vehicle_type, owner_name))
        vehicle_id = cursor.lastrowid

    cursor.execute("""
        SELECT session_id
        FROM parking_sessions
        WHERE vehicle_id = ? AND status = 'ACTIVE'
    """, (vehicle_id,))
    if cursor.fetchone():
        conn.close()
        return jsonify({
            "success": False,
            "message": "Vehicle already has an active parking session."
        }), 409

    cursor.execute("""
        SELECT slot_id, slot_number
        FROM parking_slots
        WHERE status = 'AVAILABLE'
        ORDER BY slot_id
        LIMIT 1
    """)
    slot = cursor.fetchone()

    if not slot:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Parking is full. No available slot."
        }), 409

    slot_id, slot_number = slot
    entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO parking_sessions
        (vehicle_id, slot_id, entry_time, status)
        VALUES (?, ?, ?, 'ACTIVE')
    """, (vehicle_id, slot_id, entry_time))

    cursor.execute("""
        UPDATE parking_slots
        SET status = 'OCCUPIED'
        WHERE slot_id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Vehicle admitted successfully.",
        "registration_no": registration_no,
        "slot_number": slot_number,
        "entry_time": entry_time,
    }), 201


@app.route("/api/exit", methods=["POST"])
def api_exit():
    """Calculate the bill for a vehicle and record successful payment."""
    data = request.get_json(silent=True) or {}
    registration_no = str(data.get("registration_no", "")).strip().upper()

    if not registration_no:
        return jsonify({"success": False, "message": "Registration number is required."}), 400

    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ps.session_id,
            ps.slot_id,
            ps.entry_time,
            v.vehicle_id,
            v.registration_no
        FROM parking_sessions ps
        JOIN vehicles v ON ps.vehicle_id = v.vehicle_id
        WHERE v.registration_no = ? AND ps.status = 'ACTIVE'
        ORDER BY ps.session_id DESC
        LIMIT 1
    """, (registration_no,))

    session = cursor.fetchone()

    if not session:
        conn.close()
        return jsonify({
            "success": False,
            "message": "No active parking session found for this vehicle."
        }), 404

    session_id, slot_id, entry_time_text, vehicle_id, _ = session
    entry_time = datetime.strptime(entry_time_text, "%Y-%m-%d %H:%M:%S")
    exit_time = datetime.now()

    duration = exit_time - entry_time
    duration_minutes = max(1, int(duration.total_seconds() // 60))

    # Same illustrative tariff used by the existing system:
    # first hour = KSh 50; each additional hour or part thereof = KSh 30.
    billable_hours = max(1, math.ceil(duration_minutes / 60))
    fee = 50 + max(0, billable_hours - 1) * 30

    payment_method = str(data.get("payment_method", "Demo Payment")).strip() or "Demo Payment"
    payment_status = str(data.get("payment_status", "SUCCESSFUL")).upper()

    if payment_status != "SUCCESSFUL":
        conn.close()
        return jsonify({
            "success": False,
            "message": "Payment was not successful. Exit barrier remains closed.",
            "fee": fee,
            "duration_minutes": duration_minutes,
        }), 402

    exit_time_text = exit_time.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE parking_sessions
        SET exit_time = ?, duration_minutes = ?, fee = ?, status = 'COMPLETED'
        WHERE session_id = ?
    """, (exit_time_text, duration_minutes, fee, session_id))

    cursor.execute("""
        INSERT INTO payments
        (session_id, amount, payment_method, payment_time, payment_status)
        VALUES (?, ?, ?, ?, 'SUCCESSFUL')
    """, (session_id, fee, payment_method, exit_time_text))

    cursor.execute("""
        UPDATE parking_slots
        SET status = 'AVAILABLE'
        WHERE slot_id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Payment successful. Exit barrier authorized.",
        "registration_no": registration_no,
        "duration_minutes": duration_minutes,
        "fee": fee,
        "payment_status": "SUCCESSFUL",
        "exit_time": exit_time_text,
    })


@app.route("/api/history", methods=["GET"])
def api_history():
    """Return completed parking sessions for the future history page."""
    conn = connect_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            v.registration_no,
            ps.entry_time,
            ps.exit_time,
            ps.duration_minutes,
            ps.fee,
            ps.status
        FROM parking_sessions ps
        JOIN vehicles v ON ps.vehicle_id = v.vehicle_id
        WHERE ps.status = 'COMPLETED'
        ORDER BY ps.session_id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "registration_no": row[0],
            "entry_time": row[1],
            "exit_time": row[2],
            "duration_minutes": row[3],
            "fee": row[4],
            "status": row[5],
        }
        for row in rows
    ])


# ============================================================
# START WEB SERVER
# ============================================================

if __name__ == "__main__":
    create_tables()
    create_default_slots(number_of_slots=10)

    print("Modern Automated Parking Management System")
    print("Web backend is running.")
    print("Open http://127.0.0.1:5000 in your browser.")

    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))

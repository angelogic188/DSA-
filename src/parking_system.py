"""
Modern Automated Parking Management System

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
# MAIN MENU
# ============================================================

def main():
    """Run the parking management system."""
    create_tables()
    create_default_slots(number_of_slots=10)

    while True:
        print("\n")
        print("==============================================")
        print("   MODERN AUTOMATED PARKING MANAGEMENT SYSTEM")
        print("==============================================")
        print("1. Display parking availability")
        print("2. Display detailed slot status")
        print("3. Vehicle entry")
        print("4. Vehicle exit")
        print("5. View parking history")
        print("6. Add vehicle to waiting queue")
        print("7. View waiting queue")
        print("8. Exit program")
        print("==============================================")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            display_availability()

        elif choice == "2":
            display_detailed_status()

        elif choice == "3":
            vehicle_entry()

        elif choice == "4":
            vehicle_exit()

        elif choice == "5":
            display_history()

        elif choice == "6":
            add_to_waiting_queue()

        elif choice == "7":
            show_waiting_queue()

        elif choice == "8":
            print("Closing parking management system...")
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please select 1-8.")


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":
    main()

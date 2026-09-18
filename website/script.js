async function loadParkingAvailability() {
    const availability =document.getElementById("availability"); 
    try{
        const response=await
        fetch("/api/parking");
    
    
        const data=await response.json();
        document.getElementById("total-slots").textContent = data.total_slots;
        document.getElementById("available-slots").textContent = data.available_slots;
        document.getElementById("occupied-slots").textContent = data.occupied_slots;

        console.log("Parkig data received:",data);
        console.log("Parkig data received:",data);

const parkingSlots = document.getElementById("parking-slots");

parkingSlots.innerHTML = "";

data.slots.forEach(slot => {
    const slotBox = document.createElement("div");

    slotBox.className = `slot ${slot.status.toLowerCase()}`;

    slotBox.innerHTML = `
        <div class="slot-number">${slot.slot_number}</div>
        <div class="slot-status">${slot.status}</div>
    `;
    
    parkingSlots.appendChild(slotBox);
});

availability.textContent =
    `${data.available_slots} parking slots available out of ${data.total_slots}.`;

        availability.textContent=
        `${data.available_slots}parking slots available out of ${data.total_slots}.`;
    }catch(error){
        console.error("Connection error:",error);
        alert(error.message);
        
      availability.textContent=
      "Unable to connect to parking system.";
    }
    
}

loadParkingAvailability();
document.getElementById("entry-form").addEventListener("submit", async function(event) {
    event.preventDefault();

    const registration_no = document.getElementById("registration").value.trim();
    const vehicle_type = document.getElementById("vehicle-type").value;
    const owner_name = document.getElementById("owner-name").value.trim();

    try {
        const response = await fetch("/api/entry", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                registration_no: registration_no,
                vehicle_type: vehicle_type,
                owner_name: owner_name
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || "Vehicle entry failed.");
        }

        document.getElementById("entry-message").textContent =
            `${data.message} Assigned slot: ${data.slot_number}`;

        document.getElementById("entry-form").reset();

        loadParkingAvailability();

    } catch (error) {
        console.error("Entry error:", error);

        document.getElementById("entry-message").textContent =
            error.message;
    }
});


document.getElementById("exit-form").addEventListener("submit", async function(event) {
    event.preventDefault();

    const registration_no = document.getElementById("exit-registration").value.trim();

    try {
        const response = await fetch("/api/exit", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                registration_no: registration_no,
                payment_method: "Demo Payment",
                payment_status: "SUCCESSFUL"
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || "Vehicle exit failed.");
        }

        document.getElementById("exit-message").textContent =
            data.message;

        document.getElementById("payment-vehicle").textContent =
            data.registration_no;

        document.getElementById("parking-duration").textContent =
            `${data.duration_minutes} minutes`;

        document.getElementById("amount-payable").textContent =
            `KSh ${data.fee}`;

        document.getElementById("payment-message").textContent =
            "Payment successful. Exit barrier authorized.";

        document.getElementById("exit-form").reset();

        loadParkingAvailability();
        loadParkingHistory();

    } catch (error) {
        console.error("Exit error:", error);

        document.getElementById("exit-message").textContent =
            error.message;
    }
});


async function loadParkingHistory() {
    try {
        const response = await fetch("/api/history");

        if (!response.ok) {
            throw new Error("Could not load parking history.");
        }

        const history = await response.json();

        const historyBody = document.getElementById("history-body");

        historyBody.innerHTML = "";

        history.forEach(record => {
            const row = document.createElement("tr");

            row.innerHTML = `
                <td>${record.registration_no}</td>
                <td>${record.entry_time}</td>
                <td>${record.exit_time}</td>
                <td>${record.duration_minutes} minutes</td>
                <td>KSh ${record.fee}</td>
            `;

            historyBody.appendChild(row);
        });

    } catch (error) {
        console.error("History error:", error);
    }
}

loadParkingHistory();
console.log("Payment button code loaded");
document.getElementById("payment-button").addEventListener("click", function() {
    const paymentMessage = document.getElementById("payment-message");

    paymentMessage.textContent =
        "Payment has already been confirmed. Exit barrier is authorized.";
});
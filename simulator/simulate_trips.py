# simulator/simulate_trips.py

import json, time, random
from azure.eventhub import EventHubProducerClient, EventData

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
CONN_STR       = "Endpoint=sb://ns-cst8917-lab4.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=G8CWes5TrWVcpEJsB2VvzLkwxWzJo5Ta7+AEhORIX1Q="
EVENTHUB_NAME  = "eh-cst8917-trips"

# ─── HELPER TO GENERATE FAKE TRIPS ───────────────────────────────────────────────
def generate_trip():
    return {
        "ContentData": {
            "vendorID":        f"V{random.randint(1,20):03d}",
            "tripDistance":    f"{random.uniform(0.2, 15.0):.2f}",
            "passengerCount":  str(random.randint(1,6)),
            "paymentType":     random.choice(["1","2"])
        }
    }

# ─── SENDER ─────────────────────────────────────────────────────────────────────
def send_trips(num_events=20, delay_s=0.5):
    producer = EventHubProducerClient.from_connection_string(
        conn_str=CONN_STR, eventhub_name=EVENTHUB_NAME
    )
    with producer:
        batch = producer.create_batch()
        for i in range(num_events):
            trip = generate_trip()
            batch.add(EventData(json.dumps(trip)))
            # Send batch if it’s full
            if batch.size_in_bytes >= batch.max_size_in_bytes:
                producer.send_batch(batch)
                batch = producer.create_batch()
            time.sleep(delay_s)
        # Send any remaining events
        if len(batch) > 0:
            producer.send_batch(batch)
    print(f"✅ Sent {num_events} trip events to {EVENTHUB_NAME}")

if __name__ == "__main__":
    # Adjust num_events and delay_s as needed
    send_trips(num_events=50, delay_s=0.2)

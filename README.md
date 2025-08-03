# CST8917 Lab 4 – Real-Time Trip Event Analysis
Student: Daniel Abou-Assaly
Youtube link:

## Azure Resources and How to Provision Them

| Resource Name             | Type                                | Purpose                                                          | How to fill (portal steps)                                                                                                                          |
|---------------------------|-------------------------------------|------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| **ns-cst8917-lab4**       | Event Hubs Namespace                | Container for your `eh-cst8917-trips` Event Hub                  | 1. In Azure Portal, click **Create a resource** → search “Event Hubs Namespace”.<br>2. Name it `ns-cst8917-lab4`, choose your RG & region, SKU “Standard”.<br>3. Click **Review + create** → **Create**. |
| **eh-cst8917-trips**      | Event Hub                           | Ingests trip JSON events                                         | 1. In **ns-cst8917-lab4** page, under **Entities**, click **+ Event hub**.<br>2. Name it `eh-cst8917-trips`, leave defaults, click **Create**.                                           |
| **fa-cst8917-lab4**       | Function App                        | Hosts your `analyze_trip` HTTP-triggered Python Function         | 1. **Create a resource** → “Function App”.<br>2. Name it `fa-cst8917-lab4`, select your RG, runtime Python 3.11, Linux, and ASP-rgcst8917lab4-b527 plan.<br>3. **Review + create** → **Create**. |
| **ASP-rgcst8917lab4-b527**| App Service Plan                    | Compute plan for your Function App                               | 1. In **Function App** creation, under **Hosting**, click **Create new** plan.<br>2. Name it `ASP-rgcst8917lab4-b527`, choose “Consumption (Serverless)”.                                    |
| **stfcst8917lab4**        | Storage Account                     | Stores function state, logs, triggers                            | 1. In **Function App** creation, under **Storage**, click **Create new**.<br>2. Name it `stfcst8917lab4`, choose Standard – StorageV2.<br>3. Complete creation.                             |
| **la-cst8917-tripmonitor**| Logic App                           | Orchestrates Event Hub → Function → Teams flow                   | 1. **Create a resource** → “Logic App (Consumption)”.<br>2. Name it `la-cst8917-tripmonitor`, select RG & region.<br>3. **Review + create** → **Create**.                                   |
| **eventhubs**             | API Connection (Event Hubs)         | Authenticates Logic App to your Event Hub                        | 1. In Logic App designer, click **+ Add connection** → choose “Event Hubs”.<br>2. Authorize with your subscription and select `ns-cst8917-lab4`.                                          |
| **teams**                 | API Connection (Microsoft Teams)    | Authenticates Logic App to post Adaptive Cards in Teams          | 1. In Logic App designer, click **+ Add connection** → “Microsoft Teams”.<br>2. Sign in with your tenant account and grant permissions.                                                  |
| **Application Insights**  | Application Insights instance       | Captures logs & metrics for Function App & Logic App             | 1. **Create a resource** → “Application Insights”.<br>2. Name it `fa-cst8917-lab4-ai`, select your RG & region, set resource type to “General”.<br>3. Create.                         |

### Architecture Overview


1. **Event Hub** (`eh-cst8917-trips`) collects incoming trip JSON messages.  
2. **Logic App** (`la-cst8917-tripmonitor`) polls the hub every minute, or can be manually triggered for a demo.  
3. Inside the Logic App:
   - **Trigger**: “When events are available in Event Hub” (Content-Type=`application/json`, splitOn=`@triggerBody()`).
   - **HTTP**: Posts each event’s `.ContentData` payload to the Azure Function endpoint.
   - **For each** response object:
     - **Condition** on `isInteresting`:
       - **False** →  “No Issues” Adaptive Card  
       - **True** → nested **Condition** on `insights` array:
         - Contains `SuspiciousVendorActivity` →  Suspicious card  
         - Else →  Interesting card  

### Function Overview `analyze_trip`

- Setup & Imports
 Registers the FunctionApp, allows anonymous HTTP calls, and pulls in logging/JSON libraries.


```bash
import azure.functions as func
import logging, json

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

```
- Entry Point & Input Normalization
Reads the raw request body as JSON.
Ensures we always work with a list of trip objects, even if only one was sent.

```bash
@app.route(route="")
def analyze_trip(req: func.HttpRequest) -> func.HttpResponse:
    try:
        input_data = req.get_json()
        trips = input_data if isinstance(input_data, list) else [input_data]
        results = []

```
- Extract & Convert Fields
Pulls our nested trip payload out of the Event Hub envelope.
Converts distance to a float, passenger count to an int, and payment type to string.

```bash
        for record in trips:
            trip = record.get("ContentData", {})
            vendor = trip.get("vendorID")
            distance = float(trip.get("tripDistance", 0))
            passenger_count = int(trip.get("passengerCount", 0))
            payment = str(trip.get("paymentType"))
```
- Flagging Logic
Builds a list of “insights” by checking each rule in turn:

Long trips (>10 miles)

Large groups (>4 pax)

Cash payments ("2")

Very short cash trips (<1 mile) flagged as suspicious

```bash
            insights = []
            if distance > 10:
                insights.append("LongTrip")
            if passenger_count > 4:
                insights.append("GroupRide")
            if payment == "2":
                insights.append("CashPayment")
            if payment == "2" and distance < 1:
                insights.append("SuspiciousVendorActivity")

```
- Result Construction
Packages all extracted fields plus the computed insights into one object.
Sets isInteresting true if any insights exist, and builds a human-readable summary.
```bash
            results.append({
                "vendorID": vendor,
                "tripDistance": distance,
                "passengerCount": passenger_count,
                "paymentType": payment,
                "insights": insights,
                "isInteresting": bool(insights),
                "summary": f"{len(insights)} flags: {', '.join(insights)}" if insights else "Trip normal"
            })
```
- Return Response
Sends the full array of result objects back to the caller (the Logic App).
```bash
        return func.HttpResponse(
            body=json.dumps(results),
            status_code=200,
            mimetype="application/json"
        )

```
- Error Handling
Catches any unexpected error, logs it, and returns a 400 with the error message.
```bash
    except Exception as e:
        logging.error(f"Error processing trip data: {e}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=400)

```
- Trip Simulator (simulate_trips.py)
Generates and sends a configurable number of realistic, randomized taxi trip events to your Event Hub: it constructs each event’s JSON payload with a random vendor ID, a floating-point trip distance between 0.2 and 15 miles, a passenger count of 1–6, and a random payment type (cash or card), batches these into payloads that respect the Event Hub’s maximum message size, and streams them at a controlled rate (default 50 events at 0.2 s intervals) so you can stress-test your end-to-end Logic App → Function → Teams pipeline under near real-world conditions.

```bash
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


```
## Example Input & Output

**Input** (Event Hub JSON message):
```json
{
  "ContentData": {
    "vendorID": "V004",
    "tripDistance": "0.50",
    "passengerCount": "1",
    "paymentType": "2"
  }
}
```

**Output**
```json
[
  {
    "vendorID": "V004",
    "tripDistance": 0.5,
    "passengerCount": 1,
    "paymentType": "2",
    "insights": ["CashPayment","SuspiciousVendorActivity"],
    "isInteresting": true,
    "summary": "2 flags: CashPayment, SuspiciousVendorActivity"
  }
]

```

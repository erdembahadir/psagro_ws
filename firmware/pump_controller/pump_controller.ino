#include "DHT.h"

// 4 pompa + 2 akis sensoru (ZJ-S401) + 1 DHT11
const int pumps[] = {14, 15, 16, 17};
const int pumpCount = 4;
const unsigned long MAX_ON_MS = 300000;
unsigned long pumpOffTime[pumpCount];

const int flowPins[] = {2, 3};
const int flowCount = 2;
volatile unsigned long flowPulses[2] = {0, 0};
const float PULSES_PER_LITER = 5880.0;     // KALIBRE ET
const unsigned long TELEMETRY_MS = 1000;
unsigned long lastTelemetry = 0;

#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);
const unsigned long CLIMATE_MS = 2000;
unsigned long lastClimate = 0;

void flowISR0() { flowPulses[0]++; }
void flowISR1() { flowPulses[1]++; }

String buf = "";

void allOff() {
  for (int i = 0; i < pumpCount; i++) { digitalWrite(pumps[i], LOW); pumpOffTime[i] = 0; }
}
void pumpOn(int i, unsigned long durationMs) {
  if (durationMs == 0 || durationMs > MAX_ON_MS) durationMs = MAX_ON_MS;
  digitalWrite(pumps[i], HIGH); pumpOffTime[i] = millis() + durationMs;
}
void pumpOff(int i) { digitalWrite(pumps[i], LOW); pumpOffTime[i] = 0; }
void sendStatus() {
  Serial.print("STATUS");
  for (int i = 0; i < pumpCount; i++) { Serial.print(","); Serial.print(digitalRead(pumps[i]) == HIGH ? 1 : 0); }
  Serial.println();
}
void handleCommand(String cmd) {
  cmd.trim(); cmd.toUpperCase();
  if (cmd.length() == 0) return;
  if (cmd == "ALL_ON")  { for (int i = 0; i < pumpCount; i++) pumpOn(i, MAX_ON_MS); Serial.println("ACK:ALL_ON"); return; }
  if (cmd == "ALL_OFF") { allOff(); Serial.println("ACK:ALL_OFF"); return; }
  if (cmd == "STATUS")  { sendStatus(); return; }
  if (cmd.charAt(0) == 'P') {
    int us = cmd.indexOf('_');
    if (us < 2) { Serial.println("ERR:BAD_CMD"); return; }
    int pumpNo = cmd.substring(1, us).toInt();
    int idx = pumpNo - 1;
    if (idx < 0 || idx >= pumpCount) { Serial.println("ERR:BAD_PUMP"); return; }
    String rest = cmd.substring(us + 1);
    if (rest == "ON")  { pumpOn(idx, MAX_ON_MS); Serial.print("ACK:"); Serial.println(cmd); }
    else if (rest == "OFF") { pumpOff(idx); Serial.print("ACK:"); Serial.println(cmd); }
    else if (rest.startsWith("RUN_")) { unsigned long ms = (unsigned long) rest.substring(4).toInt(); pumpOn(idx, ms); Serial.print("ACK:"); Serial.println(cmd); }
    else { Serial.println("ERR:BAD_CMD"); }
    return;
  }
  Serial.println("ERR:UNKNOWN");
}

void sendTelemetry() {
  for (int i = 0; i < flowCount; i++) {
    noInterrupts();
    unsigned long p = flowPulses[i];
    flowPulses[i] = 0;
    interrupts();
    float lpm = (p / PULSES_PER_LITER) * (60000.0 / TELEMETRY_MS);
    Serial.print("FLOW,"); Serial.print(i + 1); Serial.print(",");
    Serial.print(p); Serial.print(","); Serial.println(lpm, 2);
  }
}

void sendClimate() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) { Serial.println("CLIMATE,ERR"); return; }
  Serial.print("CLIMATE,"); Serial.print(t, 1); Serial.print(","); Serial.println(h, 1);
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < pumpCount; i++) { pinMode(pumps[i], OUTPUT); digitalWrite(pumps[i], LOW); pumpOffTime[i] = 0; }
  for (int i = 0; i < flowCount; i++) pinMode(flowPins[i], INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(flowPins[0]), flowISR0, RISING);
  attachInterrupt(digitalPinToInterrupt(flowPins[1]), flowISR1, RISING);
  dht.begin();
  Serial.println("READY");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { if (buf.length() > 0) { handleCommand(buf); buf = ""; } }
    else { buf += c; if (buf.length() > 40) buf = ""; }
  }
  unsigned long now = millis();
  for (int i = 0; i < pumpCount; i++) {
    if (pumpOffTime[i] != 0 && now >= pumpOffTime[i]) {
      digitalWrite(pumps[i], LOW); pumpOffTime[i] = 0;
      Serial.print("OFF:P"); Serial.println(i + 1);
    }
  }
  if (now - lastTelemetry >= TELEMETRY_MS) { lastTelemetry = now; sendTelemetry(); }
  if (now - lastClimate >= CLIMATE_MS) { lastClimate = now; sendClimate(); }
}

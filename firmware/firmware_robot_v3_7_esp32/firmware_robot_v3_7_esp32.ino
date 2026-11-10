/*
  Firmware v3.6 - CORIOT GAMES 2026 - Codigo Rescate - ROBOT REAL (ESP32)

  CAMBIOS RESPECTO A v3.4:
  - Secuencia persistente en NVS (Preferences). Incrementa en cada reporte y no se reinicia al encender.
  - Configuracion por MQTT: suscripcion a coriot/robot/E01/config (retenido) con {equipo,intento}.
  - Control por un solo interruptor de encendido: encender = arranque, apagar = parada. Sin boton.
  - Tiempo: 470 s envia reporte final y detiene motores; 480 s detiene todo.
  - Borde negro ACTIVO: el limite exterior es negro; 2 lecturas seguidas.
  - Servo: verificar que en reposo y en derribo quepa en 13x18x20 cm (TODO medir).
  - Vision: la laptop (celular con IP Webcam) detecta; el robot recibe las detecciones por MQTT en coriot/vision/E01.
  - Reporte: el robot arma el JSON y lo publica en coriot/robot/E01/reporte. La laptop lo reenvia al servidor y responde ACK. Sin ACK no hay derribo.
  - Derribo: lo decide el robot con sus sensores.
  - Color: sensor TCS34725 por I2C.
  - Distancia: 3 HC-SR04.
  - Motores: DRV8871 x2 directo de bateria.
  - Watchdog de 8 s.
  - Vision: se exige h >= 1.2 * w; las derribadas no cuentan.
  - 24 posiciones de victima (X), 6 por cuadrante. Coordenadas PROVISIONALES (TODO).

  PENDIENTE: formato definitivo del JSON y broker/tema oficiales; calibracion de COLOR_CAL y CLEAR_MIN;
  barrido por 4 puntos relativos por cuadrante + 360 (TODO); dedup por rumbo +/-15 deg (TODO);
  recepcion de coordenadas de X por MQTT (TODO); dimensiones del servo (TODO).
*/


#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <math.h>
#include <esp_task_wdt.h>
#include <Preferences.h>

// =====================================================================
//  CONFIGURACIÓN
// =====================================================================

// ---- Red / MQTT ----
// Broker: el de la competencia o el local de pruebas. Esta versión usa el
// broker para tres cosas: visión (laptop -> robot), reporte (robot -> laptop)
// y ACK (laptop -> robot). El envío al servidor de la competencia lo hace la laptop.
const char* WIFI_SSID      = "CORIOT_RED";     // CAMBIAR por la red real
const char* WIFI_PASS      = "CAMBIAR";
const char* MQTT_HOST      = "192.168.1.10";   // IP del broker (laptop o servidor)
const uint16_t MQTT_PORT   = 1883;
const char* MQTT_USER      = "";
const char* MQTT_PASS      = "";
const char* EQUIPO_ID      = "E01";
const char* MQTT_TOPIC_VISION = "coriot/vision/E01";        // laptop -> robot
const char* MQTT_TOPIC      = "coriot/robot/E01/reporte";  // robot -> laptop
const char* MQTT_TOPIC_ACK  = "coriot/robot/E01/ack";      // laptop -> robot
const char* MQTT_TOPIC_CFG   = "coriot/robot/E01/config";    // laptop -> robot (retained)
char INTENTO_ID[8]        = "I1";                // lo asigna el juez (por MQTT config)
char EQUIPO_ID_RAM[16]     = "E01";               // se sobrescribe por config MQTT
bool configValida          = false;               // true cuando llego {"equipo","intento"}
const bool  USAR_ACK_SERVIDOR = true;            // el derribo espera ACK de la laptop
const unsigned long ACK_MS = 8000;

// ---- Pines ----
const byte PIN_START = 0;
const byte PIN_L_IN1 = 25, PIN_L_IN2 = 26;       // DRV8871 izquierdo
const byte PIN_R_IN1 = 27, PIN_R_IN2 = 13;       // DRV8871 derecho
const byte PIN_SERVO = 33;
const byte PIN_BAT = 32;                          // divisor de batería
const byte PIN_ENC_L_A = 34, PIN_ENC_L_B = 35;   // solo entrada: pull-up externo 10k
const byte PIN_ENC_R_A = 36, PIN_ENC_R_B = 39;   // solo entrada: pull-up externo 10k
const byte PIN_TRIG_F = 18, PIN_ECHO_F = 19;     // HC-SR04 frente
const byte PIN_TRIG_L = 16, PIN_ECHO_L = 17;     // HC-SR04 izquierda
const byte PIN_TRIG_R = 4,  PIN_ECHO_R = 14;     // HC-SR04 derecha
const byte PIN_SDA = 21, PIN_SCL = 22;           // MPU-6050 (0x68) y TCS34725 (0x29)

// ---- Mecánica (MEDIR) ----
const float RUEDA_DIAM_MM   = 43.0f;   // llanta de 43 mm (según la lista)
const float DIST_RUEDAS_MM  = 100.0f;  // entre centros de las dos ruedas
const float TICKS_REV       = 420.0f;  // ticks por vuelta de rueda: 7 PPR x2 flancos x 30:1. CONFIRMAR
const float MM_POR_TICK     = 3.14159265f * RUEDA_DIAM_MM / TICKS_REV;
const float SENSOR_OFFSET_MM = 60.0f;  // TCS34725 por delante del centro del robot
const float US_OFFSET_MM     = 70.0f;  // HC-SR04 frontal por delante del centro
const bool MOTOR_INV_L = false, MOTOR_INV_R = false;   // invertir si la rueda gira al revés (prueba 't')
const int  ENC_SIGNO_L = 1, ENC_SIGNO_R = 1;           // invertir si los ticks salen negativos al avanzar
const float GYRO_SIGNO = 1.0f;                         // invertir si el yaw baja al girar a la izquierda (prueba 'g')
const bool DECAIMIENTO_LENTO = true;                   // modo de PWM del DRV8871

// ---- Motores (CALIBRAR) ----
// Batería 2S directa a VM (7.4-8.4 V). PWM_MAX limita el voltaje promedio cerca de 6 V.
const int   PWM_MAX = 180;
const int   PWM_MIN = 45;
const float V_MAX_MM_S = 300.0f;       // velocidad a PWM_MAX (medir con 'v')
const float KFF = (PWM_MAX - PWM_MIN) / V_MAX_MM_S;
const float KP = 0.15f, KI = 0.60f;
const float INTEG_MAX = 80.0f;
const unsigned long CTL_MS = 20;       // lazo rápido de control
const unsigned long TICK_MS = 50;      // lazo de decisiones

// ---- Velocidades (mm/s) ----
const float V_CRUCERO = 150.0f;
const float V_ACERCAR = 70.0f;
const float V_ACC = 110.0f;
const float V_GIRO_MIN = 45.0f, V_GIRO_MAX = 130.0f;
const float KG = 2.2f;                 // ganancia de giro (mm/s por grado)
const float K_RUMBO = 3.0f;            // corrección de rumbo (mm/s por grado)
const float K_VIS = 0.12f;             // corrección por cámara al acercarse (mm/s por unidad)
const float GIRO_TOL_DEG = 2.0f;
const unsigned long US_TIMEOUT_US = 9000UL;   // HC-SR04: ~150 cm de alcance útil

// ---- Misión ----
const unsigned long LIMITE_MS = 470000UL;   // 7 min 50 s: envia reporte final y detiene motores
const unsigned long LIMITE_TOTAL_MS = 480000UL; // 8 min: detiene todo (reglamento)
const int   OBST_CM = 15;
const int   PARADA_CM = 6;                  // distancia de golpe (según alcance del servo)
const unsigned long PERDIDA_MS = 1000;
const float MAX_ACERCAR_MM = 700.0f;
const byte  SCAN_PASOS = 12;                // 12 vistas de 30 grados
const unsigned long SCAN_PAUSA_MS = 900;
const unsigned long IGNORAR_MS = 2500;
const byte  MAX_ENVIOS = 3;
const byte  MAX_GOLPES = 3;
const byte  PUNTOS_POR_Q = 4;               // puntos de barrido por cuadrante (4: 25%/75% de cada eje)
const unsigned long WP_TIMEOUT_MS = 25000;
const float WP_TOL_MM = 80.0f;
const float SNAP_TOL_MM = 250.0f;
const int   SERVO_REPOSO = 0, SERVO_GOLPE = 90;
const bool  CIERRE_ANTICIPADO = false;      // zona gris del reglamento

// ---- Visión (laptop -> robot por MQTT) ----
// Formato de línea: D,v,c,x,w,h,conf
//   v: 1 = detección, 0 = sin figura
//   c: H o S
//   x: centro horizontal normalizado 0..1000 (500 = centro del frame)
//   w, h: ancho y alto de la caja en la misma escala 0..1000
//   conf: confianza 0..100
const byte  FILTRO_MIN = 5;                 // 5 de los últimos 7 fotogramas
const int   CONF_MIN = 50;
const int   ASPECTO_MIN_X10 = 12;           // h >= 1.2 * w: figura de pie (x10 para evitar decimales)
const unsigned long VISION_VIVA_MS = 1000;
const int   ZONA_CENTRO = 90;               // tolerancia de centrado (sobre 1000)
const int   W_MIN_GOLPE = 0;                // ancho mínimo a PARADA_CM. MEDIR; 0 = inactivo

// ---- Color (TCS34725 por I2C) ----
// Los valores brutos (clear, r, g, b) dependen de la luz. Calibrar con 'k'.
const bool  COLOR_CALIBRADO = false;
const float CLEAR_MIN = 40.0f;              // clear por debajo: sin lectura válida (conteo bruto)
const byte  COLOR_CONF = 3;                 // lecturas seguidas para confirmar un cuadrante
const float COLOR_CAL[4][3] = {             // proporciones r,g,b de cada cuadrante (CALIBRAR)
  {0.55f, 0.22f, 0.23f},                    // ROJO
  {0.20f, 0.30f, 0.50f},                    // AZUL
  {0.28f, 0.45f, 0.27f},                    // VERDE
  {0.45f, 0.40f, 0.15f}                     // AMARILLO
};
const byte  TCS_ADDR = 0x29;
const bool  BORDE_NEGRO = true;             // el límite exterior de la pista es negro (tabla oficial)
const byte  BORDE_LECTURAS = 2;             // lecturas seguidas de NEGRO para confirmar el borde

// ---- Posición inicial en START (ajustar a cómo se coloca el robot) ----
const float START_X_MM = 100.0f, START_Y_MM = 100.0f, START_TH_DEG = 0.0f;

// ---- Giroscopio / batería ----
const byte  MPU_ADDR = 0x68;
const float BAT_FACTOR = 3.0f;              // VERIFICAR con el multímetro y las resistencias del divisor
const float BAT_MIN_V = 7.0f;               // aviso
const float BAT_CORTE_V = 6.6f;             // por debajo, el DRV8871 puede dejar de funcionar: se termina la misión

// =====================================================================
//  IDENTIFICADORES Y VARIABLES GLOBALES
// =====================================================================
const byte ROJO = 0, AZUL = 1, VERDE = 2, AMARILLO = 3, NEGRO = 4;
const char* const NOMBRE[5] = {"rojo", "azul", "verde", "amarillo", "NEGRO"};
const int CX[4] = {500, 1500, 500, 1500};
const int CY[4] = {1500, 1500, 500, 500};

const byte E_ESPERA = 0, E_NAVEGAR = 1, E_SCAN = 2, E_ACERCAR = 3,
           E_REPORTAR = 4, E_DERRIBAR = 5, E_FIN = 6;
const char* const NOM_ESTADO[7] = {"ESPERA", "NAVEGAR", "SCAN", "ACERCAR",
                                   "REPORTAR", "DERRIBAR", "FIN"};
const byte A_AVANZ = 1, A_GIRO = 2, A_PAUSA = 3;

const float DEG2RAD = 0.01745329252f, RAD2DEG = 57.2957795f;

const byte M_IN1[2] = {PIN_L_IN1, PIN_R_IN1};
const byte M_IN2[2] = {PIN_L_IN2, PIN_R_IN2};
const bool M_INV[2] = {MOTOR_INV_L, MOTOR_INV_R};

WiFiClient netClient;
PubSubClient mqtt(netClient);

byte estado = E_ESPERA;
volatile long ticks[2] = {0, 0};
long  ticksPrev[2] = {0, 0};
float vMed[2] = {0, 0}, vObj[2] = {0, 0}, integ[2] = {0, 0}, dMm[2] = {0, 0};

// pose
float xMm = START_X_MM, yMm = START_Y_MM, thDeg = START_TH_DEG, odoDist = 0;
float yawDeg = 0, gyroBias = 0;
bool  mpuOk = false;
byte  mpuFallos = 0;
unsigned long tMpu = 0;
bool  tcsOk = false;

// acciones
byte  colaTipo[4]; float colaVal[4]; byte colaN = 0;
bool  accViva = false; byte accTipo = 0, accOkCont = 0;
float accVal = 0, accRumbo = 0, accD0 = 0;
unsigned long accFin = 0;

// tiempos
unsigned long tInicio = 0, tTick = 0, tCtl = 0, tPerdida = 0, tIgnorarHasta = 0, tFase = 0;
unsigned long tProxEnvio = 0, tMqttIntento = 0, tAckLimite = 0, tAtasco = 0, tWpLimite = 0, tBat = 0;
unsigned long tUltFrame = 0;

// sensores
long  dF = 400, dL = 400, dR = 400;
byte  usIdx = 0;                 // 0 frente, 1 izquierda, 2 derecha (lectura rotativa)
bool  usTurnoLado = false;       // en ACERCAR alterna izquierda/derecha
float fClear = 0, fR = 0, fG = 0, fB = 0;
byte  colorRaw = VERDE, colorEstable = VERDE, colorCand = VERDE, colorCont = 0;
bool  atascado = false;

// visión
byte  hist = 0;
int   visX = 500, visW = 0;
float scoreH = 0, scoreS = 0;
unsigned int framesVer = 0, detVer = 0;
char  visBuf[64]; byte visLen = 0;

// misión
byte  visitado = 0, revisado = 0;
byte  heridos[4] = {0, 0, 0, 0}, suministros[4] = {0, 0, 0, 0};   // SOLO confirmadas (con derribo)
bool  pendiente = false; byte pendCuad = VERDE; char pendClase = 'H';
float figX = 0, figY = 0;
float figsX[24], figsY[24]; byte nFigs = 0;
float WP_X[24], WP_Y[24]; unsigned int wpHecho = 0, wpMascaraInicial = 0;
byte  negroCont = 0;             // lecturas seguidas de NEGRO (borde)
int   wpActual = -1, wpEnScan = -1;
byte  scanPaso = 0; bool scanEnCurso = false;
float yawsRegistrados[16]; byte nYaws = 0;
float acercarD0 = 0; bool dedupOk = false;
byte  faseDerribo = 0, golpes = 0, faseRep = 0, intentosEnvio = 0;
unsigned long secuencia = 0;
Preferences prefs;
bool  reporteSolicitado = false, finalPend = false;
byte  intentosFinal = 0, derribos = 0, erroresEnvio = 0;
bool  ackRecibido = false; unsigned long ackSeqEsperada = 0;
bool  alternaLado = true;

// =====================================================================
//  UTILIDADES
// =====================================================================
bool vencido(unsigned long t) { return (long)(millis() - t) >= 0; }

float difAng(float a, float b) {
  float d = fmodf(a - b, 360.0f);
  if (d > 180.0f) d -= 360.0f;
  if (d <= -180.0f) d += 360.0f;
  return d;
}

void irA(byte e) {
  if (e == estado) return;
  estado = e;
  Serial.print(F("-> "));
  Serial.println(NOM_ESTADO[e]);
}

byte cuadranteGeom(float x, float y) {
  if (x < 1000.0f) return (y < 1000.0f) ? VERDE : ROJO;
  return (y < 1000.0f) ? AMARILLO : AZUL;
}

long distFrenteCm() { return dF; }

// =====================================================================
//  PWM (compatible con núcleo ESP32 2.x y 3.x)
// =====================================================================
void pwmInit(byte pin, byte ch, uint32_t freq, byte bits) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttachChannel(pin, freq, bits, ch);
#else
  ledcSetup(ch, freq, bits);
  ledcAttachPin(pin, ch);
#endif
}

void pwmWrite(byte pin, byte ch, uint32_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin, duty);
#else
  ledcWrite(ch, duty);
#endif
}

void servoAngulo(int deg) {                       // 50 Hz, 16 bits, 0,5-2,4 ms
  uint32_t us = 500 + (uint32_t)deg * 1900 / 180;
  uint32_t duty = (uint32_t)((uint64_t)us * 65535 / 20000);
  pwmWrite(PIN_SERVO, 4, duty);
}

// =====================================================================
//  MOTORES (DRV8871) Y ENCODERS
// =====================================================================
void motorRaw(byte i, int u) {                    // u: -PWM_MAX..PWM_MAX, 0 = freno
  if (M_INV[i]) u = -u;
  u = constrain(u, -PWM_MAX, PWM_MAX);
  int a = abs(u);
  byte p1 = M_IN1[i], p2 = M_IN2[i], c1 = 2 * i, c2 = 2 * i + 1;
  if (u == 0) { pwmWrite(p1, c1, 255); pwmWrite(p2, c2, 255); return; }   // freno (1,1)
  if (DECAIMIENTO_LENTO) {
    if (u > 0) { pwmWrite(p1, c1, 255);     pwmWrite(p2, c2, 255 - a); }
    else       { pwmWrite(p2, c2, 255);     pwmWrite(p1, c1, 255 - a); }
  } else {
    if (u > 0) { pwmWrite(p1, c1, a);       pwmWrite(p2, c2, 0); }
    else       { pwmWrite(p1, c1, 0);       pwmWrite(p2, c2, a); }
  }
}

void IRAM_ATTR isrEncL() {
  bool a = digitalRead(PIN_ENC_L_A), b = digitalRead(PIN_ENC_L_B);
  ticks[0] = ticks[0] + ((a != b) ? 1 : -1) * ENC_SIGNO_L;
}
void IRAM_ATTR isrEncR() {
  bool a = digitalRead(PIN_ENC_R_A), b = digitalRead(PIN_ENC_R_B);
  ticks[1] = ticks[1] + ((a != b) ? 1 : -1) * ENC_SIGNO_R;
}

void mover(float vl, float vr) {
  vObj[0] = constrain(vl, -V_MAX_MM_S, V_MAX_MM_S);
  vObj[1] = constrain(vr, -V_MAX_MM_S, V_MAX_MM_S);
}
void parar() { vObj[0] = 0; vObj[1] = 0; }

void ctrlRueda(byte i, float dt) {                // PI de velocidad + prealimentación
  if (fabsf(vObj[i]) < 1.0f) { integ[i] = 0; motorRaw(i, 0); return; }
  float err = vObj[i] - vMed[i];
  integ[i] = constrain(integ[i] + err * dt, -INTEG_MAX, INTEG_MAX);
  float sg = vObj[i] > 0 ? 1.0f : -1.0f;
  float u = sg * PWM_MIN + KFF * vObj[i] + KP * err + KI * integ[i];
  if (u * sg < 0) u = 0;
  motorRaw(i, (int)u);
}

// =====================================================================
//  GIROSCOPIO MPU-6050
// =====================================================================
bool mpuEscribir(byte reg, byte val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg); Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool mpuInit() {
  if (!mpuEscribir(0x6B, 0x00)) return false;     // despertar
  mpuEscribir(0x1B, 0x08);                        // +-500 grados/s (65,5 LSB)
  mpuEscribir(0x1A, 0x03);                        // filtro pasa-bajos ~44 Hz
  return true;
}

bool mpuLeerGz(float &gz) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x47);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)MPU_ADDR, 2) != 2) return false;
  int hi = Wire.read();
  int lo = Wire.read();
  gz = (int16_t)((hi << 8) | lo) / 65.5f;
  return true;
}

void mpuServicio() {
  if (!mpuOk) return;
  unsigned long us = micros();
  if (us - tMpu < 10000UL) return;                // cada 10 ms
  float dt = (us - tMpu) * 1e-6f;
  tMpu = us;
  float gz;
  if (!mpuLeerGz(gz)) { if (++mpuFallos > 20) { mpuOk = false; Serial.println(F("MPU perdido: giro por encoders")); } return; }
  mpuFallos = 0;
  if (estado == E_ESPERA) {                       // quieto: estima el sesgo
    gyroBias = 0.98f * gyroBias + 0.02f * gz;
    yawDeg = 0;
    return;
  }
  bool quietoScan = (estado == E_SCAN && accViva && accTipo == A_PAUSA &&
                     fabsf(vMed[0]) < 2.0f && fabsf(vMed[1]) < 2.0f);
  if (quietoScan && fabsf(gz - gyroBias) < 2.0f) gyroBias += 0.005f * (gz - gyroBias);
  float rate = (gz - gyroBias) * GYRO_SIGNO;
  if (fabsf(rate) < 0.08f) rate = 0;
  yawDeg += rate * dt;
  thDeg = START_TH_DEG + yawDeg;
}

// =====================================================================
//  COLOR (TCS34725 por I2C) Y ULTRASONIDO (HC-SR04 x3)
// =====================================================================
bool tcsEscribir(byte reg, byte val) {
  Wire.beginTransmission(TCS_ADDR);
  Wire.write(0x80 | reg);                         // bit de comando
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool tcsInit() {
  if (!tcsEscribir(0x00, 0x01)) return false;     // PON: encender
  delay(3);
  tcsEscribir(0x00, 0x03);                        // PON + AEN: medir
  tcsEscribir(0x01, 0xD5);                        // ATIME ~101 ms de integración
  tcsEscribir(0x0F, 0x01);                        // ganancia 4x
  return true;
}

// Lee clear, rojo, verde y azul (16 bits cada uno)
bool tcsLeer(float &c, float &r, float &g, float &b) {
  const byte regs[4] = {0x14, 0x16, 0x18, 0x1A};  // CDATAL, RDATAL, GDATAL, BDATAL
  uint16_t v[4];
  for (byte i = 0; i < 4; i++) {
    Wire.beginTransmission(TCS_ADDR);
    Wire.write(0x80 | regs[i]);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom((int)TCS_ADDR, 2) != 2) return false;
    uint8_t lo = Wire.read();
    uint8_t hi = Wire.read();
    v[i] = ((uint16_t)hi << 8) | lo;
  }
  c = v[0]; r = v[1]; g = v[2]; b = v[3];
  return true;
}

byte leerColor() {
  float c, r, g, b;
  if (!tcsOk || !tcsLeer(c, r, g, b)) { fClear = 0; return NEGRO; }
  fClear = c; fR = r; fG = g; fB = b;
  if (c < CLEAR_MIN) return NEGRO;               // sin lectura válida
  float s = r + g + b;
  if (s < 1.0f) return NEGRO;
  float rn = r / s, gn = g / s, bn = b / s;
  byte mejor = VERDE; float dmin = 1e9f;
  for (byte k = 0; k < 4; k++) {
    float d = (rn - COLOR_CAL[k][0]) * (rn - COLOR_CAL[k][0]) +
              (gn - COLOR_CAL[k][1]) * (gn - COLOR_CAL[k][1]) +
              (bn - COLOR_CAL[k][2]) * (bn - COLOR_CAL[k][2]);
    if (d < dmin) { dmin = d; mejor = k; }
  }
  return mejor;
}

long distanciaCm(byte trig, byte echo) {
  digitalWrite(trig, LOW);  delayMicroseconds(3);
  digitalWrite(trig, HIGH); delayMicroseconds(10);
  digitalWrite(trig, LOW);
  unsigned long us = pulseIn(echo, HIGH, US_TIMEOUT_US);   // ~150 cm máximo
  if (us == 0) return 400;
  return us / 58;
}

void alCambiarColor(byte prev, byte nuevo) {      // cruce de frontera: reconoce color y corrige la pose
  visitado |= (1 << nuevo);
  Serial.print(F("Color estable: ")); Serial.println(NOMBRE[nuevo]);
  bool vert = (prev == VERDE && nuevo == AMARILLO) || (prev == AMARILLO && nuevo == VERDE) ||
              (prev == ROJO && nuevo == AZUL) || (prev == AZUL && nuevo == ROJO);
  bool hor  = (prev == VERDE && nuevo == ROJO) || (prev == ROJO && nuevo == VERDE) ||
              (prev == AMARILLO && nuevo == AZUL) || (prev == AZUL && nuevo == AMARILLO);
  float th = thDeg * DEG2RAD;
  float sx = xMm + SENSOR_OFFSET_MM * cosf(th), sy = yMm + SENSOR_OFFSET_MM * sinf(th);
  if (vert && fabsf(sx - 1000.0f) < SNAP_TOL_MM) xMm = 1000.0f - SENSOR_OFFSET_MM * cosf(th);
  else if (hor && fabsf(sy - 1000.0f) < SNAP_TOL_MM) yMm = 1000.0f - SENSOR_OFFSET_MM * sinf(th);
}

void actualizarSensores() {
  if (estado == E_ACERCAR) {                      // al acercarse: frente siempre, lados alternos
    dF = distanciaCm(PIN_TRIG_F, PIN_ECHO_F);
    if (usTurnoLado) dR = distanciaCm(PIN_TRIG_R, PIN_ECHO_R);
    else             dL = distanciaCm(PIN_TRIG_L, PIN_ECHO_L);
    usTurnoLado = !usTurnoLado;
  } else {                                        // rotativo frente / izquierda / derecha
    if (usIdx == 0)      dF = distanciaCm(PIN_TRIG_F, PIN_ECHO_F);
    else if (usIdx == 1) dL = distanciaCm(PIN_TRIG_L, PIN_ECHO_L);
    else                 dR = distanciaCm(PIN_TRIG_R, PIN_ECHO_R);
    usIdx = (usIdx + 1) % 3;
  }
  colorRaw = leerColor();
  if (colorRaw == NEGRO) {                        // borde negro o sin lectura
    if (negroCont < 255) negroCont++;
    return;
  }
  negroCont = 0;
  if (colorRaw == colorCand) { if (colorCont < 255) colorCont++; }
  else { colorCand = colorRaw; colorCont = 1; }
  if (colorCont >= COLOR_CONF && colorCand != colorEstable) {
    byte prev = colorEstable;
    colorEstable = colorCand;
    alCambiarColor(prev, colorEstable);
  }
}

// =====================================================================
//  VISIÓN (MQTT desde la laptop)
// =====================================================================
void procesarLineaVision(char* s) {
  int v = 0, x = 500, w = 0, h = 0, conf = 0; char c = 'H';
  if (s[0] != 'D') return;
  int n = sscanf(s, "D,%d,%c,%d,%d,%d,%d", &v, &c, &x, &w, &h, &conf);
  if (n < 1) return;
  tUltFrame = millis();
  bool det = (v == 1 && n >= 6 && (c == 'H' || c == 'S') && conf >= CONF_MIN &&
              h * 10 >= w * ASPECTO_MIN_X10);     // figura de pie: derribadas no cuentan
  hist = ((hist << 1) | (det ? 1 : 0)) & 0x7F;     // el filtro avanza por FOTOGRAMA
  framesVer++;
  if (det) {
    detVer++;
    visX = x; visW = w;
    if (c == 'H') { scoreH = 0.7f * scoreH + conf; scoreS *= 0.7f; }
    else          { scoreS = 0.7f * scoreS + conf; scoreH *= 0.7f; }
  } else {
    scoreH *= 0.9f; scoreS *= 0.9f;
  }
}

bool visionActiva()     { return (millis() - tUltFrame) < VISION_VIVA_MS; }
bool figuraConfirmada() { return __builtin_popcount(hist) >= FILTRO_MIN; }
bool hayFigura()        { return visionActiva() && figuraConfirmada() && vencido(tIgnorarHasta); }
bool figuraVisible()    { return visionActiva() && hist != 0; }

// =====================================================================
//  ACCIONES TEMPORIZADAS / POR DISTANCIA / POR ÁNGULO (cola de 4)
// =====================================================================
void encolarAcc(byte t, float v) { if (colaN < 4) { colaTipo[colaN] = t; colaVal[colaN] = v; colaN++; } }
void limpiarAcc() { colaN = 0; accViva = false; }
bool accionActiva() { return accViva || colaN > 0; }
bool retrocediendo() { return accViva && accTipo == A_AVANZ && accVal < 0; }

void iniciarAcc(byte t, float v) {
  accViva = true; accTipo = t; accVal = v; accOkCont = 0;
  switch (t) {
    case A_AVANZ:
      accD0 = odoDist; accRumbo = thDeg;
      accFin = millis() + (unsigned long)(fabsf(v) / V_ACC * 2500.0f) + 800;
      break;
    case A_GIRO:
      accRumbo = thDeg + v;
      accFin = millis() + (unsigned long)(fabsf(v) / 90.0f * 1800.0f) + 1200;
      break;
    default:
      hist = 0;                                    // la pausa es para ver sin movimiento
      accFin = millis() + (unsigned long)v;
      parar();
      break;
  }
}

void finAcc() { accViva = false; parar(); }

void pasoAccion() {
  if (!accViva) {
    if (colaN == 0) return;
    byte t = colaTipo[0]; float v = colaVal[0];
    for (byte i = 1; i < colaN; i++) { colaTipo[i - 1] = colaTipo[i]; colaVal[i - 1] = colaVal[i]; }
    colaN--;
    iniciarAcc(t, v);
  }
  switch (accTipo) {
    case A_AVANZ: {
      float falta = accVal - (odoDist - accD0);
      float sg = accVal > 0 ? 1.0f : -1.0f;
      if (falta * sg <= 0 || vencido(accFin)) { finAcc(); break; }
      float v = sg * V_ACC;
      if (fabsf(falta) < 30.0f) v *= 0.5f;
      float corr = (sg > 0) ? constrain(K_RUMBO * difAng(accRumbo, thDeg), -40.0f, 40.0f) : 0.0f;
      mover(v - corr, v + corr);
      break;
    }
    case A_GIRO: {
      float err = difAng(accRumbo, thDeg);
      if (vencido(accFin)) { finAcc(); break; }
      if (fabsf(err) < GIRO_TOL_DEG) {
        mover(0, 0);
        if (++accOkCont >= 3) finAcc();
      } else {
        accOkCont = 0;
        float s = constrain(KG * fabsf(err), V_GIRO_MIN, V_GIRO_MAX);
        float dir = err > 0 ? 1.0f : -1.0f;
        mover(-dir * s, dir * s);                  // err>0: girar a la izquierda
      }
      break;
    }
    default:
      if (vencido(accFin)) finAcc();
      break;
  }
}

// =====================================================================
//  LAZO RÁPIDO: encoders -> odometría -> acciones -> PI de motores
// =====================================================================
void controlMotores() {
  unsigned long now = millis();
  if (now - tCtl < CTL_MS) return;
  float dt = (now - tCtl) / 1000.0f;
  tCtl = now;
  for (byte i = 0; i < 2; i++) {
    long t = ticks[i];
    long d = t - ticksPrev[i];
    ticksPrev[i] = t;
    dMm[i] = d * MM_POR_TICK;
    vMed[i] = 0.6f * vMed[i] + 0.4f * (dMm[i] / dt);
  }
  float dc = (dMm[0] + dMm[1]) * 0.5f;
  odoDist += dc;
  if (!mpuOk) thDeg += (dMm[1] - dMm[0]) / DIST_RUEDAS_MM * RAD2DEG;
  float th = thDeg * DEG2RAD;
  xMm += dc * cosf(th);
  yMm += dc * sinf(th);

  float obj = fabsf(vObj[0]) + fabsf(vObj[1]);   // atasco: hay orden pero no hay movimiento
  float med = fabsf(vMed[0]) + fabsf(vMed[1]);
  if (obj > 80.0f && med < 15.0f) {
    if (tAtasco == 0) tAtasco = now;
    else if (now - tAtasco > 800) atascado = true;
  } else tAtasco = 0;

  pasoAccion();
  ctrlRueda(0, dt);
  ctrlRueda(1, dt);
}

// =====================================================================
//  REPORTE (MQTT hacia la laptop, que lo reenvía al servidor)
// =====================================================================
void onMqtt(char* topic, byte* payload, unsigned int len) {
  char b[200];
  if (len > 199) len = 199;
  memcpy(b, payload, len); b[len] = 0;
  if (strcmp(topic, MQTT_TOPIC_CFG) == 0) {
    char* pe = strstr(b, "\"equipo\"");
    char* pi = strstr(b, "\"intento\"");
    if (!pe || !pi) { Serial.println(F("MQTT config invalida: falta equipo/intento")); return; }
    char eq[16] = {0}, in[8] = {0};
    char* qe = strchr(pe, ':'); if (qe) { qe++; while (*qe == ' ' || *qe == '"') qe++; int i=0; while (*qe && *qe != '"' && *qe != ',' && i < 15) eq[i++] = *qe++; }
    char* qi = strchr(pi, ':'); if (qi) { qi++; while (*qi == ' ' || *qi == '"') qi++; int i=0; while (*qi && *qi != '"' && *qi != ',' && i < 7) in[i++] = *qi++; }
    if (eq[0] && in[0]) {
      strncpy(EQUIPO_ID_RAM, eq, sizeof(EQUIPO_ID_RAM)-1);
      strncpy(INTENTO_ID, in, sizeof(INTENTO_ID)-1);
      configValida = true;
      Serial.print(F("Config OK equipo=")); Serial.print(EQUIPO_ID_RAM);
      Serial.print(F(" intento=")); Serial.println(INTENTO_ID);
    } else {
      Serial.println(F("MQTT config invalida: equipo/intento vacios"));
    }
    return;
  }
  if (strcmp(topic, MQTT_TOPIC_VISION) == 0) { procesarLineaVision(b); return; }
  // ACK de la laptop: busca "secuencia":N
  char* p = strstr(b, "\"secuencia\"");
  if (!p) return;
  p = strchr(p, ':');
  if (p && (unsigned long)atol(p + 1) == ackSeqEsperada) ackRecibido = true;
}

void mqttServicio() {
  if (mqtt.connected()) { mqtt.loop(); return; }
  bool quieto = (estado == E_ESPERA || estado == E_FIN || estado == E_REPORTAR ||
                 (estado == E_SCAN && accViva && accTipo == A_PAUSA));
  if (!quieto || millis() - tMqttIntento < 5000) return;   // no bloquear al robot en movimiento
  tMqttIntento = millis();
  if (WiFi.status() != WL_CONNECTED) { WiFi.reconnect(); return; }
  bool ok = (MQTT_USER[0]) ? mqtt.connect(EQUIPO_ID, MQTT_USER, MQTT_PASS) : mqtt.connect(EQUIPO_ID);
  Serial.println(ok ? F("MQTT conectado") : F("MQTT sin conexion"));
  if (ok) {
    if (USAR_ACK_SERVIDOR) mqtt.subscribe(MQTT_TOPIC_ACK);
    mqtt.subscribe(MQTT_TOPIC_VISION);
    mqtt.subscribe(MQTT_TOPIC_CFG);
  }
}

int armarJson(char* b, size_t n, const char* est, bool conPend) {
  int k = snprintf(b, n, "{\"equipo\":\"%s\",\"intento\":\"%s\",\"secuencia\":%lu,\"estado\":\"%s\",\"cuadrantes\":[",
                   EQUIPO_ID_RAM, INTENTO_ID, secuencia, est);
  for (byte c = 0; c < 4 && k < (int)n - 130; c++) {
    int h = heridos[c], s = suministros[c];
    if (conPend && pendiente && pendCuad == c) { if (pendClase == 'H') h++; else s++; }
    bool ex = ((visitado >> c) & 1) && (((revisado >> c) & 1) || h > 0 || s > 0);
    if (ex) k += snprintf(b + k, n - k, "{\"color\":\"%s\",\"explorado\":true,\"heridos\":%d,\"necesitan_suministros\":%d}", NOMBRE[c], h, s);
    else    k += snprintf(b + k, n - k, "{\"color\":\"%s\",\"explorado\":false,\"heridos\":null,\"necesitan_suministros\":null}", NOMBRE[c]);
    if (c < 3) b[k++] = ',';
  }
  k += snprintf(b + k, n - k, "]}");
  return k;
}

bool publicarReporte(const char* est, bool conPend) {
  tProxEnvio = millis() + 1100;
  char buf[760];
  armarJson(buf, sizeof(buf), est, conPend);
  Serial.print(F("MQTT> ")); Serial.println(buf);
  if (!mqtt.connected()) { Serial.println(F("  (sin conexion MQTT)")); return false; }
  return mqtt.publish(MQTT_TOPIC, buf);
}

void solicitarReporte() { reporteSolicitado = true; }

bool robotQuieto() { return fabsf(vObj[0]) < 1.0f && fabsf(vObj[1]) < 1.0f; }

void servicioReportes() {
  if (!reporteSolicitado || estado == E_REPORTAR || estado == E_DERRIBAR || estado == E_FIN) return;
  if (!vencido(tProxEnvio)) return;
  if (!robotQuieto()) return;
  secuencia++;
  prefs.putULong("seq", secuencia);
  if (publicarReporte("en_curso", false)) reporteSolicitado = false;
}

// =====================================================================
//  NAVEGACIÓN
// =====================================================================
void volverABuscar() { irA(scanEnCurso ? E_SCAN : E_NAVEGAR); }

void iniciarScan() {
  parar();
  scanPaso = 0;
  nYaws = 0;
  scanEnCurso = true;
  Serial.println(F("Escaneo 360 con la camara"));
  irA(E_SCAN);
}

void iniciarAcercar() {
  parar();
  tPerdida = millis();
  dedupOk = false;
  acercarD0 = odoDist;
  irA(E_ACERCAR);
}

void evitarObstaculo() {
  Serial.println(F("Obstaculo: rodeo"));
  parar(); limpiarAcc();
  float lado;
  if (labs(dL - dR) < 3) { lado = alternaLado ? 1.0f : -1.0f; alternaLado = !alternaLado; }
  else lado = (dL > dR) ? 1.0f : -1.0f;            // gira hacia el lado más libre
  encolarAcc(A_AVANZ, -60.0f);
  encolarAcc(A_GIRO, lado * 70.0f);
  encolarAcc(A_AVANZ, 150.0f);
}

void manejarBorde() {                              // solo si BORDE_NEGRO = true
  Serial.println(F("BORDE negro: retrocedo y giro al centro"));
  parar(); limpiarAcc();
  corregirPorBorde();
  float rumboCentro = atan2f(1000.0f - yMm, 1000.0f - xMm) * RAD2DEG;
  encolarAcc(A_AVANZ, -70.0f);
  encolarAcc(A_GIRO, difAng(rumboCentro, thDeg));
}

void corregirPorBorde() {
  float th = thDeg * DEG2RAD;
  float ox = SENSOR_OFFSET_MM * cosf(th), oy = SENSOR_OFFSET_MM * sinf(th);
  float sx = xMm + ox, sy = yMm + oy;
  float d0 = sx, d1 = 2000.0f - sx, d2 = sy, d3 = 2000.0f - sy;
  float m = d0; byte k = 0;
  if (d1 < m) { m = d1; k = 1; }
  if (d2 < m) { m = d2; k = 2; }
  if (d3 < m) { m = d3; k = 3; }
  if (m > 200.0f) return;
  if (k == 0) xMm = 0.0f - ox;
  else if (k == 1) xMm = 2000.0f - ox;
  else if (k == 2) yMm = 0.0f - oy;
  else yMm = 2000.0f - oy;
}

void elegirWaypoint() {
  wpActual = -1;
  bool faltaCuad = (revisado & 0x0F) != 0x0F;
  for (byte pasada = 0; pasada < 2 && wpActual < 0; pasada++) {
    float mejor = 1e9f;
    for (byte i = 0; i < (PUNTOS_POR_Q * 4); i++) {
      if ((wpHecho >> i) & 1) continue;
      if (pasada == 0 && faltaCuad && ((revisado >> (i / PUNTOS_POR_Q)) & 1)) continue;
      float d = hypotf(WP_X[i] - xMm, WP_Y[i] - yMm);
      if (d < mejor) { mejor = d; wpActual = i; }
    }
    if (!faltaCuad) break;
  }
  if (wpActual < 0) {
    wpHecho = wpMascaraInicial;
    Serial.println(F("Puntos completos: nueva vuelta"));
    return;
  }
  tWpLimite = millis() + WP_TIMEOUT_MS;
  Serial.print(F("Objetivo punto ")); Serial.print(wpActual);
  Serial.print(F(" (")); Serial.print(WP_X[wpActual], 0); Serial.print(F(",")); Serial.print(WP_Y[wpActual], 0);
  Serial.println(F(")"));
}

// =====================================================================
//  ESTADOS
// =====================================================================
void pasoNavegar() {
  if (hayFigura()) {
    Serial.println(F("Figura detectada (5 de 7)"));
    iniciarAcercar();
    return;
  }
  if (wpActual < 0) { elegirWaypoint(); if (wpActual < 0) { parar(); return; } }

  float dx = WP_X[wpActual] - xMm, dy = WP_Y[wpActual] - yMm;
  if (hypotf(dx, dy) < WP_TOL_MM) {
    parar();
    wpEnScan = wpActual;
    iniciarScan();
    return;
  }
  if (vencido(tWpLimite)) {
    Serial.println(F("Punto inalcanzable: lo salto"));
    wpHecho |= (1U << wpActual);
    wpActual = -1;
    return;
  }
  long frente = distFrenteCm();
  if (frente < OBST_CM) { evitarObstaculo(); return; }

  float err = difAng(atan2f(dy, dx) * RAD2DEG, thDeg);
  if (fabsf(err) > 30.0f) {
    float s = constrain(KG * fabsf(err), V_GIRO_MIN, V_GIRO_MAX);
    float dir = err > 0 ? 1.0f : -1.0f;
    mover(-dir * s, dir * s);
  } else {
    float v = (frente < 30) ? V_CRUCERO * 0.6f : V_CRUCERO;
    float corr = constrain(K_RUMBO * err, -50.0f, 50.0f);
    mover(v - corr, v + corr);
  }
}

// ¿Están revisadas las 6 X del cuadrante q?
bool cuadranteCompleto(byte q) {
  for (byte k = 0; k < PUNTOS_POR_Q; k++) {
    if (!((wpHecho >> (q * PUNTOS_POR_Q + k)) & 1)) return false;
  }
  return true;
}

void pasoScan() {
  if (hayFigura()) {
    parar();
    Serial.println(F("Figura detectada durante el escaneo"));
    iniciarAcercar();
    return;
  }
  if (scanPaso >= SCAN_PASOS) {
    scanEnCurso = false;
    if (wpEnScan >= 0) { wpHecho |= (1U << wpEnScan); wpEnScan = -1; }
    wpActual = -1;
    byte q = cuadranteGeom(xMm, yMm);
    if (cuadranteCompleto(q)) {                    // solo cuando sus 6 X están revisadas
      revisado |= (1 << q);
      Serial.print(F("Cuadrante revisado: ")); Serial.println(NOMBRE[q]);
    }
    solicitarReporte();
    irA(E_NAVEGAR);
    return;
  }
  if (scanPaso > 0) encolarAcc(A_GIRO, 360.0f / SCAN_PASOS);
  encolarAcc(A_PAUSA, (float)SCAN_PAUSA_MS);
  scanPaso++;
}

bool rumboYaRegistrado(float yaw) {
  for (byte i = 0; i < nYaws; i++) {
    float diff = fabsf(difAng(yaw, yawsRegistrados[i]));
    if (diff <= 15.0f) return true;
  }
  return false;
}

void pasoAcercar() {
  bool vis = figuraVisible();
  if (vis) tPerdida = millis();
  else if (millis() - tPerdida > PERDIDA_MS) {
    parar(); Serial.println(F("Figura perdida")); volverABuscar(); return;
  }
  if (fabsf(odoDist - acercarD0) > MAX_ACERCAR_MM) {
    parar(); Serial.println(F("Acercamiento demasiado largo: abandono"));
    tIgnorarHasta = millis() + IGNORAR_MS * 2;
    volverABuscar(); return;
  }
  long d = distFrenteCm();
  int ex = visX - 500;                             // >0: figura a la derecha

  if (d <= PARADA_CM) {
    parar();
    bool centrada = abs(ex) <= ZONA_CENTRO;
    if (vis && !centrada) {
      // figura visible pero descentrada: se centra más abajo
    } else if (vis && visW >= W_MIN_GOLPE) {
      float th = thDeg * DEG2RAD;
      float r = US_OFFSET_MM + d * 10.0f;
      figX = xMm + r * cosf(th); figY = yMm + r * sinf(th);
      pendCuad = cuadranteGeom(figX, figY);
      pendClase = (scoreH >= scoreS) ? 'H' : 'S';
      intentosEnvio = 0; faseRep = 0;
      if (nYaws < 16) { yawsRegistrados[nYaws++] = thDeg; }
      Serial.print(F("A ")); Serial.print(d); Serial.print(F(" cm: clase ")); Serial.print(pendClase);
      Serial.print(F(", cuadrante ")); Serial.println(NOMBRE[pendCuad]);
      irA(E_REPORTAR);
      return;
    } else {
      Serial.println(F("Era un obstaculo, no la figura"));
      evitarObstaculo(); volverABuscar();
      return;
    }
  }
  if (d < OBST_CM && !vis) { evitarObstaculo(); volverABuscar(); return; }

  if (abs(ex) > ZONA_CENTRO) {
    float s = constrain(0.15f * abs(ex), V_GIRO_MIN, V_GIRO_MAX);
    if (ex > 0) mover(s, -s); else mover(-s, s);
    return;
  }
  if (!dedupOk) {
    if (rumboYaRegistrado(thDeg)) {
      parar(); Serial.println(F("Figura ya contada en este barrido: la ignoro"));
      tIgnorarHasta = millis() + IGNORAR_MS * 2;
      encolarAcc(A_GIRO, 60.0f);
      volverABuscar(); return;
    }
    dedupOk = true;
  }
  float v = (d < 15) ? V_ACERCAR * 0.6f : V_ACERCAR;
  float corr = K_VIS * ex;
  mover(v + corr, v - corr);
}

void aceptarReporte() {
  faseRep = 0; faseDerribo = 0; golpes = 1;
  irA(E_DERRIBAR);
}

void falloEnvio() {
  Serial.println(F("Sin confirmacion de la laptop"));
  if (intentosEnvio < MAX_ENVIOS) return;          // reintenta con la MISMA secuencia
  erroresEnvio++;
  Serial.println(F("ERROR de envio: sin reporte confirmado NO se derriba"));
  pendiente = false; faseRep = 0;
  tIgnorarHasta = millis() + IGNORAR_MS;
  encolarAcc(A_AVANZ, -80.0f);
  encolarAcc(A_GIRO, 60.0f);
  volverABuscar();
}

void pasoReportar() {
  if (faseRep == 0) {
    if (!vencido(tProxEnvio)) return;
    intentosEnvio++;
    if (intentosEnvio == 1) { secuencia++; prefs.putULong("seq", secuencia); pendiente = true; }
    bool pub = publicarReporte("en_curso", true);  // incluye la víctima pendiente
    if (!pub) { falloEnvio(); return; }
    if (!USAR_ACK_SERVIDOR) { aceptarReporte(); return; }
    ackSeqEsperada = secuencia; ackRecibido = false;
    tAckLimite = millis() + ACK_MS; faseRep = 1;
  } else {
    if (ackRecibido) aceptarReporte();
    else if (vencido(tAckLimite)) { faseRep = 0; falloEnvio(); }
  }
}

void pasoDerribar() {
  switch (faseDerribo) {
    case 0:
      servoAngulo(SERVO_GOLPE); tFase = millis() + 500; faseDerribo = 1; break;
    case 1:
      if (vencido(tFase)) { servoAngulo(SERVO_REPOSO); tFase = millis() + 400; faseDerribo = 2; }
      break;
    case 2:
      if (vencido(tFase)) { framesVer = 0; detVer = 0; tFase = millis() + 1500; faseDerribo = 3; }
      break;
    case 3:
      if (framesVer >= 4 || vencido(tFase)) {
        bool enPie = (framesVer >= 2 && detVer * 2 > framesVer);
        if (enPie && golpes < MAX_GOLPES) {
          golpes++; Serial.println(F("Sigue en pie: otro golpe")); faseDerribo = 0;
        } else if (enPie) {
          Serial.println(F("No cae: se descarta del conteo"));
          pendiente = false; faseDerribo = 0;
          tIgnorarHasta = millis() + IGNORAR_MS * 2;
          solicitarReporte();
          encolarAcc(A_AVANZ, -80.0f); encolarAcc(A_GIRO, 60.0f);
          volverABuscar();
        } else {
          if (pendClase == 'H') heridos[pendCuad]++; else suministros[pendCuad]++;
          pendiente = false; derribos++;
          if (nFigs < 24) { figsX[nFigs] = figX; figsY[nFigs] = figY; nFigs++; }
          Serial.print(F("Derribo #")); Serial.println(derribos);
          tIgnorarHasta = millis() + IGNORAR_MS;
          solicitarReporte();
          encolarAcc(A_AVANZ, -80.0f); encolarAcc(A_GIRO, 45.0f);
          faseDerribo = 0;
          volverABuscar();
        }
      }
      break;
  }
}

byte totalConfirmadas() {
  byte t = 0;
  for (byte c = 0; c < 4; c++) t += heridos[c] + suministros[c];
  return t;
}

void terminar() {
  parar(); limpiarAcc();
  motorRaw(0, 0); motorRaw(1, 0);
  servoAngulo(SERVO_REPOSO);
  if (pendiente) Serial.println(F("Tiempo: victima pendiente SIN derribo, se excluye del reporte final"));
  pendiente = false;
  irA(E_FIN);
  secuencia++;
  prefs.putULong("seq", secuencia);
  finalPend = true; intentosFinal = 0;
  Serial.print(F("FIN. Derribos: ")); Serial.print(derribos);
  Serial.print(F(" | errores de envio: ")); Serial.println(erroresEnvio);
}

void servicioFin() {
  if (!finalPend || !vencido(tProxEnvio)) return;
  if (publicarReporte("final", false)) finalPend = false;
  else if (++intentosFinal >= 10) finalPend = false;
}

// =====================================================================
//  HERRAMIENTAS DE PUESTA A PUNTO (solo en ESPERA, por Serial)
// =====================================================================
float leerBateriaV() { return analogReadMilliVolts(PIN_BAT) * BAT_FACTOR / 1000.0f; }

void modoColor() {
  Serial.println(F("Calibracion de color: coloca el sensor sobre cada cuadrante. Cualquier tecla para salir."));
  while (!Serial.available()) {
    esp_task_wdt_reset();
    byte c = leerColor();
    float s = fR + fG + fB; if (s < 1) s = 1;
    Serial.print(F("clear=")); Serial.print(fClear, 0);
    Serial.print(F(" R=")); Serial.print(fR, 0); Serial.print(F(" G=")); Serial.print(fG, 0);
    Serial.print(F(" B=")); Serial.print(fB, 0);
    Serial.print(F(" | r,g,b=")); Serial.print(fR / s, 2); Serial.print(F(",")); Serial.print(fG / s, 2);
    Serial.print(F(",")); Serial.print(fB / s, 2);
    Serial.print(F(" -> ")); Serial.println(NOMBRE[c]);
    delay(300);
  }
  while (Serial.available()) Serial.read();
}

void testMotores() {
  for (byte i = 0; i < 2; i++) {
    long t0 = ticks[i];
    motorRaw(i, 90); delay(800); motorRaw(i, 0);
    Serial.print(i == 0 ? F("Rueda IZQ") : F("Rueda DER"));
    Serial.print(F(": ticks = ")); Serial.print(ticks[i] - t0);
    Serial.println(F("  (debe ser POSITIVO avanzando; si no, ajusta ENC_SIGNO / MOTOR_INV)"));
    delay(400);
  }
}

void testGiro() {
  Serial.println(F("Gira el robot a la IZQUIERDA con la mano: el yaw debe SUBIR (5 s)"));
  unsigned long t = millis();
  while (millis() - t < 5000) {
    esp_task_wdt_reset();
    mpuServicio();
    static unsigned long tp = 0;
    if (millis() - tp > 250) { tp = millis(); Serial.print(F("yaw=")); Serial.println(yawDeg, 1); }
  }
  Serial.print(F("sesgo estimado: ")); Serial.println(gyroBias, 3);
}

void testVelocidad() {
  Serial.println(F("Velocidad maxima: el robot AVANZA ~1 s a PWM_MAX. Pista libre. Empieza en 3 s..."));
  delay(3000);
  motorRaw(0, PWM_MAX); motorRaw(1, PWM_MAX);
  delay(400);
  long b0 = ticks[0], b1 = ticks[1];
  unsigned long t0 = millis();
  delay(400);
  float dt = (millis() - t0) / 1000.0f;
  long c0 = ticks[0], c1 = ticks[1];
  motorRaw(0, 0); motorRaw(1, 0);
  Serial.print(F("V izq = ")); Serial.print((c0 - b0) * MM_POR_TICK / dt, 0);
  Serial.print(F(" mm/s | V der = ")); Serial.print((c1 - b1) * MM_POR_TICK / dt, 0);
  Serial.println(F(" mm/s  -> usa el menor como V_MAX_MM_S (con la bateria cargada)"));
  float vmin = min((c0 - b0), (c1 - b1)) * MM_POR_TICK / dt;
  if (vmin > 1.0f) {
    Serial.print(F("Con ese V_MAX_MM_S, KFF quedara en ")); Serial.println((PWM_MAX - PWM_MIN) / vmin, 3);
  }
}

void testTicksVuelta() {
  Serial.println(F("Gira UNA rueda a mano exactamente 1 vuelta completa en los proximos 8 s..."));
  long a0 = ticks[0], a1 = ticks[1];
  unsigned long t = millis();
  while (millis() - t < 8000) { esp_task_wdt_reset(); delay(50); }
  Serial.print(F("Ticks izq = ")); Serial.print(labs(ticks[0] - a0));
  Serial.print(F(" | der = ")); Serial.print(labs(ticks[1] - a1));
  Serial.print(F("  (TICKS_REV actual = ")); Serial.print(TICKS_REV, 0);
  Serial.println(F("; la rueda que NO giraste debe quedar en ~0)"));
}

void cambiarIntento() {
  delay(50);
  while (Serial.available()) Serial.read();
  Serial.print(F("Intento actual: ")); Serial.println(INTENTO_ID);
  Serial.println(F("Escribe el nuevo ID (ej. I2) y Enter (5 s):"));
  Serial.setTimeout(5000);
  String n = Serial.readStringUntil('\n');
  n.trim();
  if (n.length() > 0 && n.length() < sizeof(INTENTO_ID) && n.indexOf('"') < 0 && n.indexOf('\\') < 0) {
    n.toCharArray(INTENTO_ID, sizeof(INTENTO_ID));
    Serial.print(F("Intento ahora: ")); Serial.println(INTENTO_ID);
  } else Serial.println(F("ID no valido, sin cambios"));
}

void esperaLoop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'k') modoColor();
    else if (c == 't') testMotores();
    else if (c == 'g') testGiro();
    else if (c == 'v') testVelocidad();
    else if (c == 'r') testTicksVuelta();
    else if (c == 'i') cambiarIntento();
    else if (c == 'b') { Serial.print(F("Bateria: ")); Serial.print(leerBateriaV(), 2); Serial.println(F(" V")); }
  }
  // v3.6: sin boton. Encender = arranque cuando llega config valida por MQTT.
  if (!configValida) {
    static unsigned long tBlink = 0;
    static bool ledOn = false;
    if (millis() - tBlink > 500) { tBlink = millis(); ledOn = !ledOn; digitalWrite(2, ledOn ? HIGH : LOW); }
    return;
  }

  tInicio = millis(); tTick = tInicio; tCtl = tInicio;
  xMm = START_X_MM; yMm = START_Y_MM; thDeg = START_TH_DEG; yawDeg = 0; odoDist = 0;
  ticksPrev[0] = ticks[0]; ticksPrev[1] = ticks[1];
  byte c = leerColor();
  colorEstable = colorCand = (c == NEGRO) ? VERDE : c;
  colorCont = COLOR_CONF;
  visitado |= (1 << colorEstable);
  Serial.print(F("START. Color inicial: ")); Serial.println(NOMBRE[colorEstable]);
  if (colorEstable != VERDE) Serial.println(F("  AVISO: se esperaba VERDE en START, revisa la calibracion"));
  iniciarScan();
}

// =====================================================================
//  ARDUINO
// =====================================================================
void setup() {
  Serial.begin(115200);
  analogSetPinAttenuation(PIN_BAT, ADC_11db);
  pinMode(PIN_ENC_L_A, INPUT); pinMode(PIN_ENC_L_B, INPUT);
  pinMode(PIN_ENC_R_A, INPUT); pinMode(PIN_ENC_R_B, INPUT);
  pinMode(PIN_TRIG_F, OUTPUT); pinMode(PIN_ECHO_F, INPUT);
  pinMode(2, OUTPUT);  // LED de espera (v3.6)
  pinMode(PIN_TRIG_L, OUTPUT); pinMode(PIN_ECHO_L, INPUT);
  pinMode(PIN_TRIG_R, OUTPUT); pinMode(PIN_ECHO_R, INPUT);

  for (byte i = 0; i < 2; i++) {
    pwmInit(M_IN1[i], 2 * i, 20000, 8);
    pwmInit(M_IN2[i], 2 * i + 1, 20000, 8);
    motorRaw(i, 0);
  }
  pwmInit(PIN_SERVO, 4, 50, 16);
  servoAngulo(SERVO_REPOSO);

  attachInterrupt(digitalPinToInterrupt(PIN_ENC_L_A), isrEncL, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_R_A), isrEncR, CHANGE);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  mpuOk = mpuInit();
  tMpu = micros();
  Serial.println(mpuOk ? F("MPU-6050 OK") : F("MPU-6050 NO responde (giro por encoders)"));
  tcsOk = tcsInit();
  Serial.println(tcsOk ? F("TCS34725 OK") : F("TCS34725 NO responde (color inactivo)"));

  // 6 posiciones X por cuadrante. PROVISIONALES (TODO): medir en la pista.
  // Offsets (mm) respecto al centro del cuadrante, en 3 columnas x 2 filas.
  const int OX[4] = {-250, -250, 250, 250};
  const int OY[4] = {-250, 250, -250, 250};
  for (byte i = 0; i < (PUNTOS_POR_Q * 4); i++) {
    byte q = i / PUNTOS_POR_Q, k = i % PUNTOS_POR_Q;
    WP_X[i] = CX[q] + OX[k];
    WP_Y[i] = CY[q] + OY[k];
  }
  wpMascaraInicial = 0;                             // las 24 X están pendientes
  wpHecho = wpMascaraInicial;

  // NVS: secuencia persistente
  prefs.begin("coriot", false);
  secuencia = prefs.getULong("seq", 0);
  Serial.print(F("Secuencia NVS: ")); Serial.println(secuencia);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) delay(200);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setBufferSize(768);
  mqtt.setSocketTimeout(2);
  Serial.println(WiFi.status() == WL_CONNECTED ? F("WiFi OK") : F("WiFi sin conexion"));

  // Watchdog: si el lazo se cuelga más de 8 s, el ESP32 reinicia y los motores quedan sin señal
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt = {};
  wdt.timeout_ms = 8000;
  wdt.idle_core_mask = 0;
  wdt.trigger_panic = true;
  esp_task_wdt_init(&wdt);
#else
  esp_task_wdt_init(8, true);
#endif
  esp_task_wdt_add(NULL);

  if (!COLOR_CALIBRADO) Serial.println(F("AVISO: color SIN CALIBRAR (comando 'k' y edita COLOR_CAL / CLEAR_MIN)"));
  Serial.print(F("Bateria: ")); Serial.print(leerBateriaV(), 2); Serial.println(F(" V"));
  Serial.println(F("Quieto en START (calibrando giroscopio). Esperando config por MQTT..."));
}

void loop() {
  esp_task_wdt_reset();
  mqttServicio();
  mpuServicio();

  if (estado == E_ESPERA) { esperaLoop(); return; }

  if (estado != E_FIN && millis() - tInicio >= LIMITE_MS) terminar();
  if (estado != E_FIN && millis() - tInicio >= LIMITE_TOTAL_MS) { Serial.println(F("TIEMPO TOTAL 480s: parada")); parar(); irA(E_FIN); }
  if (estado == E_FIN) { servicioFin(); return; }

  controlMotores();

  if (millis() - tTick < TICK_MS) return;
  tTick = millis();

  actualizarSensores();
  servicioReportes();

  if (millis() - tBat > 2000UL) {
    tBat = millis();
    float v = leerBateriaV();
    if (v < BAT_MIN_V) { Serial.print(F("AVISO bateria baja: ")); Serial.println(v, 2); }
    if (v < BAT_CORTE_V && estado != E_FIN) {
      Serial.print(F("BATERIA CRITICA: se termina la mision ")); Serial.println(v, 2);
      terminar(); return;
    }
  }
  if (CIERRE_ANTICIPADO && estado != E_REPORTAR && estado != E_DERRIBAR &&
      totalConfirmadas() >= 12 && (revisado & 0x0F) == 0x0F) { terminar(); return; }

  if (BORDE_NEGRO && tcsOk && negroCont >= BORDE_LECTURAS &&
      !retrocediendo() && estado != E_REPORTAR && estado != E_DERRIBAR) {
    negroCont = 0;
    manejarBorde(); return;
  }
  if (atascado) {
    atascado = false;
    if (!retrocediendo() && estado != E_REPORTAR && estado != E_DERRIBAR) {
      Serial.println(F("ATASCADO: retrocedo y giro"));
      limpiarAcc(); encolarAcc(A_AVANZ, -80.0f); encolarAcc(A_GIRO, 90.0f);
      return;
    }
  }
  if (accionActiva()) return;

  switch (estado) {
    case E_NAVEGAR:  pasoNavegar();  break;
    case E_SCAN:     pasoScan();     break;
    case E_ACERCAR:  pasoAcercar();  break;
    case E_REPORTAR: pasoReportar(); break;
    case E_DERRIBAR: pasoDerribar(); break;
    default: break;
  }
}

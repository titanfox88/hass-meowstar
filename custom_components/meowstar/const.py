"""Constants for the MeowStar (喵星公民) integration."""

DOMAIN = "meowstar"
MANUFACTURER = "喵星公民 MeowStar"

# Cloud API
API_BASE = "https://xiaolong618.com/api_h5/api"
API_URL_LOGIN = f"{API_BASE}/v1.user/login"
API_URL_DEVICE_MY = f"{API_BASE}/v1.device/my"
API_URL_GET_PROPERTY = f"{API_BASE}/v1.device/get_property"
API_URL_TODAY_WORK_LOG = f"{API_BASE}/v1.device/getTodayWorkLogV1"
API_URL_WSQ_STATIC = f"{API_BASE}/v1.device/getDeviceWsqStaticData"
API_URL_W_MQTT = f"{API_BASE}/v1.device/device_w_mqtt"
API_URL_MQTT = f"{API_BASE}/v1.device/device_mqtt"
API_URL_W_LOG = f"{API_BASE}/v1.device/device_w_log"
API_URL_SET_COMMAND = f"{API_BASE}/v1.device/setCommand"
API_URL_PET_MY = f"{API_BASE}/v1.pet/my"

# Config entry fields
CONF_MOBILE = "mobile"
CONF_PASSWORD = "password"

# Options
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30

# Device type families
DEVICE_TYPE_LITTER = "litter"  # M1 等 M 系列猫砂盆
DEVICE_TYPE_FEEDER = "feeder"  # W4/WS 系列喂食器

LITTER_DEVICE_TYPES = {"M1", "M2", "M"}
FEEDER_DEVICE_TYPES = {"W4", "WS231", "W"}

# Commands
CMD_CLEAN_HAND = "Clean_Hand"
CMD_ADD_CAT_LITTER = "Add_CatLitter"
CMD_STERILIZATION = "Sterilization"
CMD_FEED_FOOD = "FeedFood"
CMD_CLEAR_FOOD = "ClearFood"  # 碗内余粮重量归零（H5 同款，v=1）

DEFAULT_FEED_PORTION = 30
FEED_PORTION_OPTIONS = ["10", "30", "50", "90", "120"]
FEED_PORTION_MIN = 10
FEED_PORTION_MAX = 120
FEED_PORTION_STEP = 10
FEED_QUICK_OPTIONS = ["10", "50", "90", "120"]  # 卡片快捷档（App 同款）

ATTR_CAT_WEIGHT = "cat_weight"

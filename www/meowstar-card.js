/**
 * meowstar-card.js — 喵星公民 (MeowStar) Lovelace 自定义卡片
 *
 * 注册两种卡片：
 *   - type: custom:meowstar-litter-card  智能猫砂盆（M 系列）
 *   - type: custom:meowstar-feeder-card  智能喂食器（W 系列）
 *
 * 配置：
 *   - device: 设备 ID（device_id，编辑器里通过设备选择器选取）
 *
 * 深色卡片风格（琥珀高亮 + 半透明面板）。
 * 猫砂剩余 / 集便仓使用量以环形百分比展示，红黄蓝三色警示、方向相反：
 *   - 猫砂剩余：越少越红（<30% 红、30-60% 黄、≥60% 蓝）
 *   - 集便仓：越多越红（<60% 蓝、60-90% 黄、≥90% 红且提示换袋）
 * 卡片自动发现该设备下所有 meowstar 实体并渲染。
 */

const CARD_VERSION = '0.7.2';

console.info(
  '%c MEOWSTAR-CARD %c v' + CARD_VERSION + ' ',
  'color:#fff;background:#f5a623;font-weight:700;',
  'color:#f5a623;background:#212121;font-weight:700;'
);

// 实体 key 白名单（与集成各平台的实体 key 一致）。
// 实体 unique_id 形如 "{iot_id}_{key}"，iot_id 自身含下划线且 key 也可含下划线，
// 因此不能按“最后一个下划线”拆分，必须按已知 key 做后缀整体匹配。
const LITTER_KEYS = [
  'litter_remaining', 'litter_weight', 'chamber_temperature',
  'clean_today', 'clean_yesterday', 'clean_total',
  'toilet_today', 'toilet_yesterday', 'toilet_avg_duration',
  'last_toilet_event', 'cat_in_box', 'bin_usage', 'online',
  'clean_now', 'level_litter', 'sterilize',
];
const FEEDER_KEYS = [
  'bowl_food', 'fed_today', 'eaten_today_count', 'eaten_yesterday',
  'eaten_today', 'fed_total', 'expenses_total', 'expenses_today',
  'barn_temperature', 'barn_humidity', 'online',
  'feed_manual', 'clear_food', 'feed_portion',
];
const ALL_KEYS = [...new Set([...LITTER_KEYS, ...FEEDER_KEYS])].sort(
  (a, b) => b.length - a.length
);

// 展示单位中文化（实体内部单位保持标准单位）
const UNIT_CN = { kg: '公斤', g: '克', s: '秒', '%': '%', '°C': '℃', '元': '元' };

class MeowStarBaseCard extends HTMLElement {
  static getStubConfig() {
    return { device: '' };
  }

  setConfig(config) {
    if (!config || !config.device) {
      throw new Error('需要指定 device（设备）');
    }
    this._config = config;
    this._entityMap = null; // key -> entity_id
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._entityMap) {
      this._discover(hass).then(() => this.render());
    } else {
      this.render();
    }
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, rows: 'auto' };
  }

  async _discover(hass) {
    try {
      const [devices, entities] = await Promise.all([
        hass.callWS({ type: 'config/device_registry/list' }),
        hass.callWS({ type: 'config/entity_registry/list' }),
      ]);
      const dev = devices.find((d) => d.id === this._config.device) || {};
      this._deviceName = dev.name_by_user || dev.name || '';
      const mine = entities.filter((e) => e.device_id === this._config.device);
      const map = {};
      const uniq = {};
      for (const e of mine) {
        const uid = e.unique_id || '';
        for (const key of ALL_KEYS) {
          if (uid.endsWith('_' + key)) {
            map[key] = e.entity_id;
            break;
          }
        }
        uniq[uid] = e.entity_id;
      }
      this._entityMap = map;
      this._uniqueMap = uniq;
    } catch (err) {
      console.error('meowstar-card: cannot discover entities', err);
      this._entityMap = {};
      this._uniqueMap = {};
    }
  }

  _catStates() {
    // 猫体重实体 unique_id 形如 "{iot_id}_weight_{猫名}"，后缀即云端返回的中文猫名，
    // 不写死任何猫名，不同用户的猫自动适配。
    const out = [];
    for (const [uid, eid] of Object.entries(this._uniqueMap || {})) {
      const m = uid.match(/_weight_(.+)$/);
      if (m) {
        const s = this._hass.states[eid];
        if (s) out.push({ cat: m[1], state: s });
      }
    }
    return out;
  }

  state(key) {
    const eid = this._entityMap && this._entityMap[key];
    if (!eid) return null;
    return this._hass.states[eid] || null;
  }

  value(key, fallback = '—') {
    const s = this.state(key);
    return s && s.state !== 'unavailable' && s.state !== 'unknown' ? s.state : fallback;
  }

  unit(key) {
    const s = this.state(key);
    const u = s && s.attributes.unit_of_measurement ? s.attributes.unit_of_measurement : '';
    return UNIT_CN[u] || u;
  }

  press(key) {
    const s = this.state(key);
    if (!s) return;
    this._hass.callService('button', 'press', { entity_id: s.entity_id });
  }

  connectedCallback() {
    if (this._hass) this.render();
  }

  render() {
    if (!this._hass || !this._entityMap) return;
    // 拖动滑块期间跳过重建，避免 HA 状态刷新打断拖拽
    if (this._drag) return;
    this.innerHTML = '';
    const style = document.createElement('style');
    style.textContent = CSS;
    this.appendChild(style);
    const root = document.createElement('div');
    root.className = 'mx-card';
    root.appendChild(this._buildHeader());
    root.appendChild(this._buildBody());
    this.appendChild(root);
  }

  _buildHeader() {
    const header = document.createElement('div');
    header.className = 'mx-head';
    const online = this.state('online');
    const on = online && online.state === 'on';
    header.innerHTML = `
      <span class="mx-dot ${on ? '' : 'off'}"></span>
      <span class="mx-name">${this._deviceName || '喵星公民'}</span>
      <span class="mx-badge ${on ? '' : 'off'}">${on ? '在线' : '离线'}</span>
    `;
    return header;
  }

  /* 环形百分比 HTML（conic-gradient） */
  _ring(percent, color, label) {
    const p = Math.min(100, Math.max(0, Number(percent) || 0));
    return `
      <div class="mx-ring-wrap">
        <div class="mx-ring" style="background:conic-gradient(${color} 0%, ${color} ${p}%, rgba(255,255,255,0.08) ${p}%, rgba(255,255,255,0.08) 100%)">
          <div class="mx-ring-inner"><span class="mx-ring-num" style="color:${color}">${Math.round(p)}%</span></div>
        </div>
        <div class="mx-ring-label">${label}</div>
      </div>
    `;
  }

  /* 红黄蓝警示取色：猫砂剩余越少越危险，集便仓越多越危险（方向相反） */
  _ringColor(percent, kind) {
    const p = Number(percent) || 0;
    if (kind === 'litter') {
      if (p < 30) return '#ff6b6b'; // 红：该加砂了
      if (p < 60) return '#f5c04a'; // 黄：余量偏低
      return '#4aa8ff';             // 蓝：充足
    }
    if (p >= 90) return '#ff6b6b';  // 红：该换集便袋
    if (p >= 60) return '#f5c04a';  // 黄：接近满
    return '#4aa8ff';               // 蓝：正常
  }

  _btn(key, label, icon, primary = false) {
    const s = this.state(key);
    if (!s) return '';
    return `<div class="mx-btn ${primary ? 'primary' : ''}" data-key="${key}">
      <div class="ico"><ha-icon icon="${icon}"></ha-icon></div>
      <span>${label}</span>
    </div>`;
  }

  _bindButtons(container) {
    container.querySelectorAll('.mx-btn[data-key]').forEach((el) => {
      el.addEventListener('click', () => this.press(el.dataset.key));
    });
  }
}

/* ------------------------------------------------------------------ */
/* 猫砂盆卡片                                                          */
/* ------------------------------------------------------------------ */

class MeowStarLitterCard extends MeowStarBaseCard {
  static getConfigElement() {
    return document.createElement('meowstar-card-editor');
  }

  _buildBody() {
    const body = document.createElement('div');

    /* --- 主视觉：双环形（猫砂剩余 + 集便仓）+ 居中数据 + 气泡 --- */
    const pct = Number(this.value('litter_remaining', 0)) || 0;
    const binPct = Number(this.value('bin_usage', 0)) || 0;
    const last = this.state('last_toilet_event');
    const lastText =
      last && last.state && last.state !== 'unavailable' && last.state !== 'unknown'
        ? last.state
        : '今日暂无';

    const hero = document.createElement('div');
    hero.className = 'mx-hero';
    hero.innerHTML = `
      <div class="mx-ring-side">${this._ring(pct, this._ringColor(pct, 'litter'), '猫砂剩余')}</div>
      <div class="mx-center">
        <div class="mx-center-big">${this.value('chamber_temperature')}<span class="mx-center-unit">${this.unit('chamber_temperature')}</span></div>
        <div class="mx-center-label">舱内温度</div>
        <div class="mx-center-sub">累计清理 ${this.value('clean_total')} 次</div>
        <div class="mx-center-sub">最近如厕 ${lastText}</div>
      </div>
      <div class="mx-ring-side">${this._ring(binPct, this._ringColor(binPct, 'bin'), binPct >= 90 ? '请换集便袋' : '集便仓使用')}</div>
    `;
    body.appendChild(hero);

    /* --- 面板：清理统计 --- */
    const p1 = document.createElement('div');
    p1.className = 'mx-panel';
    p1.innerHTML = `
      <div class="mx-split">
        <div class="col">
          <div class="mx-panel-label">昨日清理次数</div>
          <div class="mx-panel-val">${this.value('clean_yesterday')}<small>次</small></div>
        </div>
        <div class="col">
          <div class="mx-panel-label">今日清理次数</div>
          <div class="mx-panel-val">${this.value('clean_today')}<small>次</small></div>
        </div>
      </div>
    `;
    body.appendChild(p1);

    /* --- 面板：如厕统计 --- */
    const avgDur = Number(this.value('toilet_avg_duration', 0)) || 0;
    const p2 = document.createElement('div');
    p2.className = 'mx-panel';
    p2.innerHTML = `
      <div class="mx-split">
        <div class="col">
          <div class="mx-panel-label">今日如厕次数</div>
          <div class="mx-panel-val">${this.value('toilet_today')}<small>次</small></div>
        </div>
        <div class="col">
          <div class="mx-panel-label">今日平均时长</div>
          <div class="mx-panel-val">${avgDur > 0 ? avgDur + '<small>秒</small>' : '—'}</div>
        </div>
      </div>
    `;
    body.appendChild(p2);

    /* --- 面板：猫咪 --- */
    const catStates = this._catStates();
    if (catStates.length) {
      const p3 = document.createElement('div');
      p3.className = 'mx-panel';
      for (const { cat, state: s } of catStates) {
        const a = s.attributes || {};
        const row = document.createElement('div');
        row.className = 'mx-cat-row';
        row.innerHTML = `
          <div class="mx-cat-ico"><ha-icon icon="mdi:cat"></ha-icon></div>
          <div class="mx-cat-info">
            <div class="mx-cat-name">${cat}</div>
            <div class="mx-cat-meta">当日 ${a['当日如厕次数'] || a['当日次数'] || '—'} 次 · 最近 ${a['最近如厕时间'] || '—'}</div>
          </div>
          <div class="mx-cat-weight">${s.state}<small>公斤</small></div>
        `;
        p3.appendChild(row);
      }
      body.appendChild(p3);
    }

    /* --- 按钮 --- */
    const btns = document.createElement('div');
    btns.className = 'mx-buttons';
    btns.innerHTML =
      this._btn('clean_now', '一键清理', 'mdi:autorenew') +
      this._btn('level_litter', '一键抚平', 'mdi:texture-box') +
      this._btn('sterilize', '深度杀菌', 'mdi:shield-bacteria');
    body.appendChild(btns);
    this._bindButtons(btns);

    return body;
  }
}

/* ------------------------------------------------------------------ */
/* 喂食器卡片                                                          */
/* ------------------------------------------------------------------ */

class MeowStarFeederCard extends MeowStarBaseCard {
  static getConfigElement() {
    return document.createElement('meowstar-card-editor');
  }

  _humidityTag(humi) {
    const h = Number(humi);
    if (!Number.isFinite(h)) return '';
    if (h > 70) return '<span class="warn">偏湿</span>';
    if (h < 30) return '<span class="warn">偏干</span>';
    return '<span class="ok">合适</span>';
  }

  _buildBody() {
    const body = document.createElement('div');

    /* --- 主视觉：气泡 + 居中余粮（原图位置，带清零）+ 气泡 --- */
    const hero = document.createElement('div');
    hero.className = 'mx-hero';
    hero.innerHTML = `
      <div class="mx-bubbles">
        <div class="mx-bubble"><b>粮仓</b> ${this.value('barn_temperature')}${this.unit('barn_temperature')} · ${this.value('barn_humidity')}${this.unit('barn_humidity')} ${this._humidityTag(this.value('barn_humidity', ''))}</div>
      </div>
      <div class="mx-center">
        <div class="mx-center-big">${this.value('bowl_food')}<span class="mx-center-unit">${this.unit('bowl_food')}</span></div>
        <div class="mx-center-label">碗内余粮 <span class="mx-clear-chip">清零</span></div>
        <div class="mx-center-sub">今日已喂 ${this.value('fed_today')}${this.unit('fed_today')} · 进食 ${this.value('eaten_today')}${this.unit('eaten_today')}</div>
      </div>
      <div class="mx-bubbles">
        <div class="mx-bubble">进食次数<br><b>${this.value('eaten_today_count')} 次</b></div>
      </div>
    `;
    body.appendChild(hero);

    /* 碗内余粮清零（两步确认，防止误触把当前重量校准为 0） */
    const clearChip = hero.querySelector('.mx-clear-chip');
    if (this.state('clear_food') && clearChip) {
      let armed = false;
      clearChip.addEventListener('click', () => {
        if (!armed) {
          armed = true;
          clearChip.textContent = '确认清零?';
          clearChip.classList.add('armed');
          setTimeout(() => {
            armed = false;
            clearChip.textContent = '清零';
            clearChip.classList.remove('armed');
          }, 4000);
        } else {
          armed = false;
          clearChip.textContent = '已发送';
          clearChip.classList.remove('armed');
          this.press('clear_food');
        }
      });
    } else if (clearChip) {
      clearChip.style.display = 'none';
    }

    /* --- 面板：累计数据 --- */
    const p1 = document.createElement('div');
    p1.className = 'mx-panel';
    p1.innerHTML = `
      <div class="mx-split">
        <div class="col">
          <div class="mx-panel-label">累计喂食</div>
          <div class="mx-panel-val">${this.value('fed_total')}<small>${this.unit('fed_total')}</small></div>
        </div>
        <div class="col">
          <div class="mx-panel-label">累计花销</div>
          <div class="mx-panel-val">${this.value('expenses_total')}<small>${this.unit('expenses_total')}</small></div>
        </div>
      </div>
    `;
    body.appendChild(p1);

    /* --- 面板：日常数据（2×2） --- */
    const p2 = document.createElement('div');
    p2.className = 'mx-panel';
    p2.innerHTML = `
      <div class="mx-grid2">
        <div class="cell">
          <div class="mx-panel-label">今日进食</div>
          <div class="mx-panel-val">${this.value('eaten_today')}<small>${this.unit('eaten_today')}</small></div>
        </div>
        <div class="cell">
          <div class="mx-panel-label">昨日进食</div>
          <div class="mx-panel-val">${this.value('eaten_yesterday')}<small>${this.unit('eaten_yesterday')}</small></div>
        </div>
        <div class="cell">
          <div class="mx-panel-label">今日花销</div>
          <div class="mx-panel-val">${this.value('expenses_today')}<small>${this.unit('expenses_today')}</small></div>
        </div>
        <div class="cell">
          <div class="mx-panel-label">今日已喂</div>
          <div class="mx-panel-val">${this.value('fed_today')}<small>${this.unit('fed_today')}</small></div>
        </div>
      </div>
    `;
    body.appendChild(p2);

    /* --- 下粮重量：线性滑块（10-120）+ 快捷档（10/50/90/120g） --- */
    const num = this.state('feed_portion');
    const cur = num ? Math.round(Number(num.state) || 30) : 30;
    const QUICK = [10, 50, 90, 120];
    if (num) {
      const section = document.createElement('div');
      section.className = 'mx-feed-ctl';
      section.innerHTML = `
        <div class="mx-slider-row">
          <span class="mx-slider-label">下粮重量</span>
          <input type="range" min="10" max="120" step="10" value="${cur}">
          <span class="mx-slider-val">${cur}<small>克</small></span>
        </div>
        <div class="mx-quick-row">
          ${QUICK.map((g) => `<span class="mx-chip${g === cur ? ' on' : ''}" data-g="${g}">${g}g</span>`).join('')}
        </div>
      `;
      const input = section.querySelector('input');
      const val = section.querySelector('.mx-slider-val');
      const setValue = (grams) => {
        val.innerHTML = grams + '<small>克</small>';
        section.querySelectorAll('.mx-chip').forEach((c) => {
          c.classList.toggle('on', Number(c.dataset.g) === grams);
        });
        this._hass.callService('number', 'set_value', {
          entity_id: num.entity_id,
          value: grams,
        });
      };
      if (!this._endDrag) {
        // 稳定引用只注册一次，避免每次渲染重复挂 window 监听
        this._endDrag = () => {
          this._drag = false;
        };
        window.addEventListener('pointerup', this._endDrag);
        window.addEventListener('pointercancel', this._endDrag);
      }
      input.addEventListener('pointerdown', () => {
        this._drag = true;
      });
      input.addEventListener('input', () => {
        const grams = Number(input.value);
        val.innerHTML = grams + '<small>克</small>';
        section.querySelectorAll('.mx-chip').forEach((c) => {
          c.classList.toggle('on', Number(c.dataset.g) === grams);
        });
      });
      input.addEventListener('change', () => setValue(Number(input.value)));
      section.querySelectorAll('.mx-chip').forEach((chip) => {
        chip.addEventListener('click', () => {
          const grams = Number(chip.dataset.g);
          input.value = String(grams);
          setValue(grams);
        });
      });
      body.appendChild(section);
    }

    /* --- 手动喂食按钮 --- */
    const btns = document.createElement('div');
    btns.className = 'mx-buttons';
    btns.innerHTML = this._btn('feed_manual', `手动喂食 ${cur}克`, 'mdi:food-drumstick', true);
    body.appendChild(btns);
    this._bindButtons(btns);

    return body;
  }
}

/* ------------------------------------------------------------------ */
/* 编辑器（设备选择）                                                   */
/* ------------------------------------------------------------------ */

class MeowStarCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config) this.render();
  }

  render() {
    if (!this._hass || !this._config) return;
    this.innerHTML = '';
    const style = document.createElement('style');
    style.textContent = 'ha-device-picker{width:100%}';
    this.appendChild(style);
    const picker = document.createElement('ha-device-picker');
    picker.hass = this._hass;
    picker.value = this._config.device || '';
    picker.label = '设备';
    picker.addEventListener('value-changed', (ev) => {
      const cfg = { ...this._config, device: ev.detail.value };
      const ev2 = new Event('config-changed', { bubbles: true, composed: true });
      Object.defineProperty(ev2, 'detail', { value: { config: cfg } });
      this.dispatchEvent(ev2);
    });
    this.appendChild(picker);
  }
}

/* ------------------------------------------------------------------ */
/* 样式（深色卡片：琥珀高亮 + 半透明面板）                              */
/* ------------------------------------------------------------------ */

const CSS = `
:host { display:block; }
.mx-card {
  background:var(--card-background-color, rgba(28,28,32,0.88));
  border-radius:var(--ha-card-border-radius, 16px);
  border:1px solid var(--ha-card-border-color, rgba(255,255,255,0.06));
  padding:16px;
  color:var(--primary-text-color, #eaeaea);
  font-size:14px;
  height:100%; box-sizing:border-box;
}
.mx-head { display:flex; align-items:center; gap:8px; }
.mx-dot { width:8px; height:8px; border-radius:50%; background:#22c55e; box-shadow:0 0 0 3px rgba(34,197,94,0.15); }
.mx-dot.off { background:#ef4444; box-shadow:0 0 0 3px rgba(239,68,68,0.15); }
.mx-name { font-size:18px; font-weight:600; }
.mx-badge { font-size:11px; padding:2px 10px; border-radius:999px; background:rgba(80,200,120,0.15); color:#5bd68a; border:1px solid rgba(80,200,120,0.35); }
.mx-badge.off { background:rgba(220,80,80,0.12); color:#e07070; border-color:rgba(220,80,80,0.35); }

.mx-hero { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:18px 0 12px; }
.mx-ring-side { flex:0 0 auto; }
.mx-ring-wrap { display:flex; flex-direction:column; align-items:center; gap:4px; }
.mx-ring { width:92px; height:92px; border-radius:50%; display:flex; align-items:center; justify-content:center; }
.mx-ring-inner { width:70px; height:70px; border-radius:50%; background:#232329; display:flex; align-items:center; justify-content:center; }
.mx-ring-num { font-size:19px; font-weight:700; }
.mx-ring-label { font-size:11px; opacity:0.55; white-space:nowrap; }

.mx-center { text-align:center; flex:1; min-width:0; }
.mx-center-big { font-size:32px; font-weight:700; color:#f5a623; line-height:1.1; }
.mx-center-unit { font-size:13px; font-weight:400; opacity:0.6; margin-left:2px; }
.mx-center-label { font-size:11px; opacity:0.55; margin-top:2px; }
.mx-center-sub { font-size:11px; opacity:0.5; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

.mx-bubbles { display:flex; flex-direction:column; gap:8px; }
.mx-bubble {
  background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08); border-radius:10px;
  padding:7px 11px; font-size:12px; line-height:1.5; max-width:160px; white-space:nowrap;
}
.mx-bubble b { color:var(--primary-text-color, #eaeaea); }
.mx-bubble .ok { color:#5bd68a; font-weight:600; }
.mx-bubble .warn { color:#e07070; font-weight:600; }

.mx-panel {
  background:rgba(255,255,255,0.045); border:1px solid rgba(255,255,255,0.06);
  border-radius:14px; padding:10px 14px; margin-top:8px;
}
.mx-split { display:flex; }
.mx-split .col { flex:1; text-align:center; padding:2px 0; }
.mx-split .col + .col { border-left:1px solid rgba(255,255,255,0.08); }
.mx-grid2 { display:grid; grid-template-columns:1fr 1fr; }
.mx-grid2 .cell { text-align:center; padding:5px 0; }
.mx-grid2 .cell:nth-child(odd) { border-right:1px solid rgba(255,255,255,0.08); }
.mx-grid2 .cell:nth-child(-n+2) { border-bottom:1px solid rgba(255,255,255,0.05); }
.mx-panel-label { font-size:11px; opacity:0.55; }
.mx-panel-val { font-size:20px; font-weight:700; margin-top:1px; line-height:1.2; }
.mx-panel-val small { font-size:11px; font-weight:400; opacity:0.5; margin-left:2px; }

.mx-cat-row { display:flex; align-items:center; gap:10px; padding:7px 2px; }
.mx-cat-row + .mx-cat-row { border-top:1px dashed rgba(255,255,255,0.08); }
.mx-cat-ico { width:30px; height:30px; border-radius:50%; background:rgba(245,166,35,0.12); display:flex; align-items:center; justify-content:center; flex:none; }
.mx-cat-ico ha-icon { --mdc-icon-size:18px; color:#f5a623; }
.mx-cat-info { flex:1; min-width:0; }
.mx-cat-name { font-size:14px; font-weight:600; }
.mx-cat-meta { font-size:10px; opacity:0.5; margin-top:1px; }
.mx-cat-weight { font-size:17px; font-weight:700; color:#f5a623; white-space:nowrap; }
.mx-cat-weight small { font-size:10px; font-weight:400; opacity:0.5; margin-left:2px; }

.mx-buttons { display:flex; justify-content:space-around; margin-top:12px; }
.mx-btn { display:flex; flex-direction:column; align-items:center; gap:5px; cursor:pointer; user-select:none; min-width:62px; }
.mx-btn .ico {
  width:46px; height:46px; border-radius:50%;
  background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.08);
  display:flex; align-items:center; justify-content:center;
  transition:transform .12s, background .15s;
}
.mx-btn:hover .ico { transform:scale(1.07); background:rgba(255,255,255,0.10); }
.mx-btn ha-icon { --mdc-icon-size:22px; color:#f5a623; }
.mx-btn span { font-size:12px; opacity:0.85; }
.mx-btn.primary .ico { width:56px; height:56px; background:rgba(245,166,35,0.12); border:1px solid rgba(245,166,35,0.4); }
.mx-btn.primary span { font-weight:600; color:#f5a623; opacity:1; }

.mx-clear-chip {
  display:inline-block; margin-left:4px; font-size:10px; padding:1px 8px;
  border-radius:999px; border:1px solid rgba(255,255,255,0.18); opacity:0.7;
  cursor:pointer; user-select:none;
}
.mx-clear-chip:hover { opacity:1; background:rgba(255,255,255,0.08); }
.mx-clear-chip.armed { color:#ff6b6b; border-color:rgba(255,107,107,0.55); opacity:1; font-weight:600; }

.mx-feed-ctl { margin-top:14px; }
.mx-slider-row { display:flex; align-items:center; gap:12px; }
.mx-slider-label { font-size:12px; opacity:0.55; white-space:nowrap; }
.mx-slider-row input[type=range] {
  flex:1; -webkit-appearance:none; appearance:none; height:4px; border-radius:999px;
  background:rgba(255,255,255,0.15); outline:none; accent-color:#f5a623;
}
.mx-slider-row input[type=range]::-webkit-slider-thumb {
  -webkit-appearance:none; appearance:none;
  width:18px; height:18px; border-radius:50%;
  background:#f5a623; border:2px solid #212121;
  box-shadow:0 2px 6px rgba(0,0,0,0.4); cursor:pointer;
}
.mx-slider-row input[type=range]::-moz-range-thumb {
  width:18px; height:18px; border-radius:50%;
  background:#f5a623; border:2px solid #212121;
  box-shadow:0 2px 6px rgba(0,0,0,0.4); cursor:pointer;
}
.mx-slider-val { font-size:16px; font-weight:700; color:#f5a623; min-width:52px; text-align:right; white-space:nowrap; }
.mx-slider-val small { font-size:11px; font-weight:400; opacity:0.6; margin-left:1px; }

.mx-quick-row { display:flex; gap:8px; margin-top:8px; }
.mx-chip {
  flex:1; text-align:center; font-size:12px; padding:5px 0; border-radius:9px;
  background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.09);
  color:inherit; opacity:0.8; cursor:pointer; user-select:none;
}
.mx-chip:hover { background:rgba(255,255,255,0.09); }
.mx-chip.on { background:rgba(245,166,35,0.14); border-color:rgba(245,166,35,0.45); color:#f5a623; font-weight:600; opacity:1; }
`;

/* ------------------------------------------------------------------ */
/* 注册                                                                */
/* ------------------------------------------------------------------ */

customElements.define('meowstar-litter-card', MeowStarLitterCard);
customElements.define('meowstar-feeder-card', MeowStarFeederCard);
customElements.define('meowstar-card-editor', MeowStarCardEditor);

window.customCards = window.customCards || [];
window.customCards.push(
  {
    type: 'meowstar-litter-card',
    name: '喵星公民·猫砂盆',
    description: '智能猫砂盆状态与控制卡片（环形砂量/集便仓警示、如厕、体重、一键清理）',
  },
  {
    type: 'meowstar-feeder-card',
    name: '喵星公民·喂食器',
    description: '智能喂食器状态与控制卡片（余粮/进食/温湿度/线性下粮重量/清零）',
  }
);
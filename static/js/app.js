/* 狗狗管理平台 · 前端交互 */
(function () {
  'use strict';

  /* ------------------------------------------------ 打卡 / 编辑弹窗 */
  var modalEl = document.getElementById('ckModal');
  var ck = modalEl ? new bootstrap.Modal(modalEl) : null;

  var TITLES = {
    feed: '🍚 记录投喂',
    potty: '💩 记录排泄',
    train: '🎾 记录训练',
    weight: '⚖️ 记录体重',
    water: '💧 记录饮水',
    note: '📝 记录备注'
  };

  /* 各类型用到的输入框，重置时统一清空 */
  var FIELDS = {
    feed: ['feed_amount', 'feed_eaten', 'feed_food', 'feed_snack', 'feed_supplement'],
    potty: ['potty_loc'],
    train: ['train_minutes', 'train_success', 'train_total', 'train_reward', 'train_adjust'],
    weight: ['weight_kg'],
    water: ['water_ml']
  };
  var SELECTS = ['potty_kind', 'potty_score', 'potty_trigger', 'train_command',
                 'train_env', 'train_distract'];

  function show(kind) {
    modalEl.querySelectorAll('[data-sec]').forEach(function (s) {
      s.classList.toggle('d-none', s.dataset.sec !== kind);
    });
  }

  function el(id) { return document.getElementById(id); }

  /* 本地时区的今天（不能用 toISOString，那是 UTC 会差一天） */
  function todayISO() {
    var n = new Date();
    return n.getFullYear() + '-' + ('0' + (n.getMonth() + 1)).slice(-2) + '-' + ('0' + n.getDate()).slice(-2);
  }

  function setVal(id, v) {
    var e = el(id);
    if (e) e.value = (v === null || v === undefined) ? '' : v;
  }

  /* 下拉框回填：选项里没有就临时补一个，避免编辑时值丢失 */
  function setSelect(id, v) {
    var e = el(id);
    if (!e) return;
    v = (v === null || v === undefined) ? '' : String(v);
    var found = false;
    for (var i = 0; i < e.options.length; i++) {
      if (e.options[i].value === v) { found = true; break; }
    }
    if (!found && v !== '') {
      var o = document.createElement('option');
      o.value = v;
      o.textContent = v;
      o.setAttribute('data-tmp', '1');
      e.appendChild(o);
    }
    e.value = v;
  }

  /* 清空弹窗，避免上一次编辑的值泄漏到下一次打卡 */
  function resetForm() {
    el('ckEditId').value = '';
    Object.keys(FIELDS).forEach(function (k) {
      FIELDS[k].forEach(function (id) { setVal(id, ''); });
    });
    setVal('ckNote', '');
    ['potty_success', 'potty_blood'].forEach(function (id) {
      var c = el(id);
      if (c) c.checked = false;
    });
    if (el('potty_success')) el('potty_success').checked = true;
    if (el('train_distract')) el('train_distract').value = '3';
    if (el('potty_score')) el('potty_score').value = '3';
    el('ckEditHint').classList.add('d-none');
    el('ckSaveBtn').textContent = '保存记录';
    SELECTS.forEach(function (id) {
      var e = el(id);
      if (e) {
        e.querySelectorAll('option[data-tmp]').forEach(function (o) { o.remove(); });
      }
    });
  }

  /* 编辑模式：按已有记录回填表单 */
  function fillForm(kind, d, ev) {
    d = d || {};
    if (kind === 'feed') {
      setVal('feed_amount', d.amount);
      setVal('feed_eaten', d.eaten);
      setVal('feed_food', d.food);
      setVal('feed_snack', d.snack);
      setVal('feed_supplement', d.supplement);
    } else if (kind === 'potty') {
      setSelect('potty_kind', d.kind || '便');
      setSelect('potty_score', d.score === undefined || d.score === null ? '3' : d.score);
      setSelect('potty_trigger', d.trigger || '');
      setVal('potty_loc', d.location);
      if (el('potty_success')) el('potty_success').checked = !!d.success;
      if (el('potty_blood')) el('potty_blood').checked = !!d.blood;
    } else if (kind === 'train') {
      setSelect('train_command', d.command || '');
      setVal('train_minutes', d.minutes);
      setVal('train_success', d.success);
      setVal('train_total', d.total);
      setSelect('train_env', d.env || '室内');
      setSelect('train_distract', d.distraction || '3');
      setVal('train_reward', d.reward);
      setVal('train_adjust', d.adjust);
    } else if (kind === 'weight') {
      setVal('weight_kg', d.kg);
    } else if (kind === 'water') {
      setVal('water_ml', d.ml);
    }
    setVal('ckNote', ev.note || '');
  }

  window.openCheckin = function (btn) {
    if (!ck) return;
    resetForm();
    var kind = btn.dataset.kind;
    var t = btn.dataset.time;
    if (!t) {
      var n = new Date();
      t = ('0' + n.getHours()).slice(-2) + ':' + ('0' + n.getMinutes()).slice(-2);
    }
    el('ckTitle').textContent = TITLES[kind] || '记录';
    el('ckType').value = kind;
    el('ckTime').value = t;
    el('ckDay').value = btn.dataset.day || '';
    el('ckKey').value = btn.dataset.key || '';
    el('ckDayInput').value = btn.dataset.day || todayISO();
    el('ckTimeInput').value = t;
    show(kind);
    if (kind === 'feed') {
      var fa = el('feed_amount');
      if (fa && btn.dataset.def && !fa.value) fa.value = btn.dataset.def;
    }
    if (kind === 'train') {
      if (!el('train_success').value) el('train_success').value = '4';
      if (!el('train_total').value) el('train_total').value = '5';
      if (!el('train_minutes').value) el('train_minutes').value = '5';
    }
    ck.show();
  };

  /* 编辑已有记录 */
  window.openEdit = function (btn) {
    if (!ck) return;
    var ev;
    try {
      ev = JSON.parse(btn.dataset.event);
    } catch (e) {
      alert('记录数据读取失败');
      return;
    }
    resetForm();
    el('ckEditId').value = ev.id;
    el('ckType').value = ev.type;
    el('ckTime').value = ev.time || '';
    el('ckDay').value = ev.day || '';
    el('ckDayInput').value = ev.day || todayISO();
    el('ckTimeInput').value = ev.time || '';
    el('ckTitle').textContent = '✏️ 编辑记录（' + (TITLES[ev.type] || ev.type).replace(/^\S+\s/, '') + '）';
    fillForm(ev.type, ev.data, ev);
    show(ev.type);
    el('ckEditHint').classList.remove('d-none');
    el('ckSaveBtn').textContent = '保存修改';
    ck.show();
  };

  function val(id) {
    var e = el(id);
    if (!e) return '';
    return String(e.value).trim();
  }
  function num(id) {
    var v = val(id);
    return v === '' ? null : Number(v);
  }

  function collect(kind) {
    var d = {};
    if (kind === 'feed') {
      d.amount = num('feed_amount');
      d.eaten = num('feed_eaten');
      d.food = val('feed_food');
      d.snack = val('feed_snack');
      d.supplement = val('feed_supplement');
    } else if (kind === 'potty') {
      d.kind = val('potty_kind') || '便';
      d.success = el('potty_success').checked;
      d.score = num('potty_score');
      d.blood = el('potty_blood').checked;
      d.location = val('potty_loc');
      d.trigger = val('potty_trigger');
      if (d.kind === '尿') d.score = null;
    } else if (kind === 'train') {
      d.command = val('train_command');
      d.minutes = num('train_minutes');
      d.env = val('train_env');
      d.distraction = num('train_distract');
      d.success = num('train_success') || 0;
      d.total = num('train_total') || 0;
      d.reward = val('train_reward');
      d.adjust = val('train_adjust');
    } else if (kind === 'weight') {
      d.kg = num('weight_kg');
      if (!d.kg) { alert('请填体重'); return null; }
    } else if (kind === 'water') {
      d.ml = num('water_ml');
    }
    return d;
  }

  window.submitCheckin = function () {
    var kind = el('ckType').value;
    var data = collect(kind);
    if (data === null) return;
    var editId = el('ckEditId').value;
    var body = {
      dog_id: Number(el('ckDog').value),
      type: kind,
      time: el('ckTimeInput').value || el('ckTime').value,
      day: el('ckDayInput').value || el('ckDay').value,
      note: val('ckNote'),
      data: data
    };
    var url = '/api/checkin';
    if (editId) {
      url = '/api/event/update';
      body.id = Number(editId);
    }
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) {
        ck.hide();
        location.reload();
      } else {
        alert('保存失败：' + (res.error || '未知错误'));
      }
    }).catch(function () { alert('网络错误，记录没有保存'); });
  };

  /* ------------------------------------------------ 删除记录 */
  window.delEvent = function (id) {
    if (!confirm('删除这条记录？删了就找不回来了。')) return;
    fetch('/api/event/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，记录没有删除'); });
  };

  /* ------------------------------------------------ 复制 */
  window.copyText = function (elId, btn) {
    var el = document.getElementById(elId);
    if (!el) return;
    var t = el.innerText;
    var done = function () {
      var old = btn.textContent;
      btn.textContent = '✅ 已复制';
      setTimeout(function () { btn.textContent = old; }, 1500);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(done).catch(function () { fallback(t, done); });
    } else {
      fallback(t, done);
    }
  };

  function fallback(t, done) {
    var ta = document.createElement('textarea');
    ta.value = t;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) { alert('复制失败，请手动选择'); }
    document.body.removeChild(ta);
  }

  window.copyAll = function (btn) {
    var blocks = document.querySelectorAll('.pblock pre');
    var t = '';
    blocks.forEach(function (b) {
      var title = b.closest('.pblock').querySelector('.p-title');
      t += '\n\n========== ' + (title ? title.textContent : '') + ' ==========\n' + b.innerText;
    });
    copyTextFromString(t, btn);
  };

  function copyTextFromString(t, btn) {
    var done = function () {
      var old = btn.textContent;
      btn.textContent = '✅ 全部已复制';
      setTimeout(function () { btn.textContent = old; }, 1800);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(done).catch(function () { fallback(t, done); });
    } else {
      fallback(t, done);
    }
  }

  /* ------------------------------------------------ 快速体重打卡 */
  window.quickWeight = function (dogId, day) {
    var v = prompt('输入当前体重（kg）');
    if (!v) return;
    fetch('/api/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dog_id: dogId, type: 'weight', day: day, data: { kg: Number(v) } })
    }).then(function () { location.reload(); });
  };

  /* ------------------------------------------------ 通用快速打卡（单字段） */
  window.quickHit = function (dogId, day, time, type, data) {
    fetch('/api/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dog_id: dogId, type: type, day: day, time: time, data: data || {} })
    }).then(function () { location.reload(); });
  };

  /* ------------------------------------------------ 狗狗管理状态 */
  var stEl = document.getElementById('stModal');
  var stModal = stEl ? new bootstrap.Modal(stEl) : null;

  window.openStatusModal = function (btn) {
    if (!stModal) return;
    var d;
    try {
      d = JSON.parse(btn.dataset.dog);
    } catch (e) {
      alert('狗狗信息读取失败');
      return;
    }
    document.getElementById('stDogId').value = d.id;
    document.getElementById('stDogName').textContent = d.name || '';
    document.getElementById('stCurrent').textContent = d.status || '在养';
    document.getElementById('stNew').value = d.status || '在养';
    document.getElementById('stNote').value = '';
    stModal.show();
  };

  window.submitStatus = function () {
    var id = Number(document.getElementById('stDogId').value);
    var st = document.getElementById('stNew').value;
    var note = document.getElementById('stNote').value.trim();
    fetch('/api/dog/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dog_id: id, status: st, note: note })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) {
        alert('保存失败：' + (res.error || '未知错误'));
        return;
      }
      if (!res.changed) {
        stModal.hide();
        alert('状态没变，没有改动。');
        return;
      }
      location.reload();
    }).catch(function () { alert('网络错误，状态没有保存'); });
  };

  /* ------------------------------------------------ 狗狗日记 */
  var deEl = document.getElementById('diaryEditModal');
  var deModal = deEl ? new bootstrap.Modal(deEl) : null;
  var diaryReloadMonth = null;

  window.openDiaryEdit = function (btn) {
    if (!deModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.diary); }
    catch (e) { alert('日记数据读取失败'); return; }
    document.getElementById('deId').value = d.id;
    document.getElementById('deDay').value = d.day || todayISO();
    document.getElementById('deMood').value = d.mood || '';
    document.getElementById('dePlace').value = d.place || '';
    document.getElementById('deTitle').value = d.title || '';
    document.getElementById('deContent').value = d.content || '';
    diaryReloadMonth = (d.day || '').slice(0, 7);
    deModal.show();
  };

  window.submitDiaryEdit = function () {
    var body = {
      id: Number(document.getElementById('deId').value),
      day: document.getElementById('deDay').value,
      mood: document.getElementById('deMood').value,
      place: document.getElementById('dePlace').value.trim(),
      title: document.getElementById('deTitle').value.trim(),
      content: document.getElementById('deContent').value.trim()
    };
    fetch('/api/diary/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { deModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.delMedia = function (id) {
    if (!confirm('删掉这个附件？文件会从硬盘上一并删除。')) return;
    fetch('/api/diary/media/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有删除'); });
  };

  /* ------------------------------------------------ 狗狗记账 */
  var exEl = document.getElementById('exModal');
  var exModal = exEl ? new bootstrap.Modal(exEl) : null;

  function exNumOr(v) { return v === '' || v === null ? null : Number(v); }

  window.exTip = function () {
    var sel = document.getElementById('exCategory');
    var box = document.getElementById('exTipBox');
    if (!sel || !box) return;
    var o = sel.options[sel.selectedIndex];
    box.textContent = o ? (o.dataset.tip || '') : '';
  };

  window.openExpenseNew = function () {
    if (!exModal) return;
    document.getElementById('exTitle').textContent = '＋ 记一笔';
    document.getElementById('exId').value = '';
    document.getElementById('exDay').value = todayISO();
    document.getElementById('exAmount').value = '';
    document.getElementById('exCategory').value = '狗粮';
    document.getElementById('exItem').value = '';
    document.getElementById('exQty').value = '';
    document.getElementById('exUnit').value = '';
    document.getElementById('exShop').value = '';
    document.getElementById('exPay').value = '';
    document.getElementById('exNote').value = '';
    exTip();
  };

  window.openExpenseEdit = function (btn) {
    if (!exModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.ex); }
    catch (e) { alert('记录数据读取失败'); return; }
    document.getElementById('exTitle').textContent = '✏️ 编辑消费记录';
    document.getElementById('exId').value = d.id;
    document.getElementById('exDay').value = d.day || todayISO();
    document.getElementById('exAmount').value = (d.amount === null || d.amount === undefined) ? '' : d.amount;
    document.getElementById('exCategory').value = d.category || '狗粮';
    document.getElementById('exItem').value = d.item || '';
    document.getElementById('exQty').value = (d.qty === null || d.qty === undefined) ? '' : d.qty;
    document.getElementById('exUnit').value = d.unit || '';
    document.getElementById('exShop').value = d.shop || '';
    document.getElementById('exPay').value = d.pay_method || '';
    document.getElementById('exNote').value = d.note || '';
    exTip();
    exModal.show();
  };

  window.submitExpense = function () {
    var id = document.getElementById('exId').value;
    var amt = document.getElementById('exAmount').value;
    if (!amt || Number(amt) <= 0) { alert('金额要大于 0'); return; }
    var body = {
      id: id ? Number(id) : undefined,
      dog_id: Number(document.getElementById('exDogId').value),
      day: document.getElementById('exDay').value,
      amount: Number(amt),
      category: document.getElementById('exCategory').value,
      item: document.getElementById('exItem').value.trim(),
      qty: exNumOr(document.getElementById('exQty').value),
      unit: document.getElementById('exUnit').value.trim(),
      shop: document.getElementById('exShop').value.trim(),
      pay_method: document.getElementById('exPay').value,
      note: document.getElementById('exNote').value.trim()
    };
    var url = id ? '/api/expense/update' : '/api/expense';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { exModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.delExpense = function (id) {
    if (!confirm('删除这条消费记录？')) return;
    fetch('/api/expense/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有删除'); });
  };

})();

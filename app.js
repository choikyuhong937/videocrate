/* ===================================================
   조기축구 감독실 - app.js
   =================================================== */

// ── 상태 ──────────────────────────────────────────
let players = [];          // 전체 선수 명단
let selectedIds = new Set(); // 오늘 경기 선택된 선수 ID

// ── 초기화 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadFromStorage();
  renderRoster();
  loadApiKeyStatus();
});

// ── 페이지 전환 ───────────────────────────────────
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.add('active');
  document.querySelector(`.nav-btn[onclick*="${name}"]`).classList.add('active');

  if (name === 'match') renderMatchPlayers();
}

// ── 로컬 스토리지 ─────────────────────────────────
function loadFromStorage() {
  try {
    players = JSON.parse(localStorage.getItem('soccer_players') || '[]');
  } catch { players = []; }
}
function saveToStorage() {
  localStorage.setItem('soccer_players', JSON.stringify(players));
}
function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

// ── API 키 ────────────────────────────────────────
function saveApiKey() {
  const key = document.getElementById('api-key-input').value.trim();
  if (!key) { showApiStatus('API 키를 입력해주세요.', false); return; }
  localStorage.setItem('gemini_api_key', key);
  document.getElementById('api-key-input').value = '';
  showApiStatus('✅ API 키가 저장되었습니다.', true);
}
function loadApiKeyStatus() {
  const key = localStorage.getItem('gemini_api_key');
  if (key) showApiStatus('✅ API 키가 등록되어 있습니다.', true);
}
function showApiStatus(msg, ok) {
  const el = document.getElementById('api-key-status');
  el.textContent = msg;
  el.className = 'status-text ' + (ok ? 'ok' : 'err');
}
function getApiKey() {
  return localStorage.getItem('gemini_api_key') || '';
}

// ── 데이터 초기화 ─────────────────────────────────
function clearAllData() {
  if (!confirm('선수 명단을 모두 삭제하시겠습니까?')) return;
  players = [];
  selectedIds.clear();
  saveToStorage();
  renderRoster();
  renderMatchPlayers();
}

// ══════════════════════════════════════════════════
//  선수 명단 렌더링
// ══════════════════════════════════════════════════
function renderRoster() {
  const grid = document.getElementById('player-list');
  if (!players.length) {
    grid.innerHTML = '<div class="empty-state">선수를 추가해주세요. 오른쪽 위 [+ 선수 추가] 버튼을 눌러보세요!</div>';
    return;
  }
  grid.innerHTML = players.map(p => playerCardHTML(p, false)).join('');
}

function renderMatchPlayers() {
  const grid = document.getElementById('match-player-list');
  if (!players.length) {
    grid.innerHTML = '<div class="empty-state">선수 명단 탭에서 먼저 선수를 추가해주세요.</div>';
    return;
  }
  grid.innerHTML = players.map(p => playerCardHTML(p, true)).join('');
  updateSelectedCount();
}

function playerCardHTML(p, selectable) {
  const isSelected = selectedIds.has(p.id);
  const levelEmoji = { '초급': '🌱', '중급': '⚽', '고급': '🌟' }[p.level] || '';
  const speedTag = p.speed !== '보통' ? `<span class="tag">${p.speed}</span>` : '';
  const staminaTag = p.stamina !== '보통' ? `<span class="tag">${p.stamina} 체력</span>` : '';
  const skills = (p.skills || []).map(s => `<span class="tag green">${s}</span>`).join('');
  const styles = (p.styles || []).map(s => `<span class="tag">${s}</span>`).join('');

  const clickAttr = selectable ? `onclick="toggleSelect('${p.id}')"` : '';
  const checkCircle = selectable
    ? `<div class="select-check">${isSelected ? '✓' : ''}</div>`
    : `<div class="player-actions">
         <button class="btn-icon" title="수정" onclick="openEditPlayerModal('${p.id}')">✏️</button>
         <button class="btn-icon" title="삭제" onclick="deletePlayer('${p.id}')">🗑️</button>
       </div>`;

  return `
    <div class="player-card ${isSelected && selectable ? 'selected' : ''}" ${clickAttr}>
      ${checkCircle}
      <div class="player-card-top">
        <div class="player-name-wrap">
          ${p.number ? `<span class="player-number">${p.number}</span>` : ''}
          <span class="player-name">${p.name}</span>
        </div>
      </div>
      <div>
        <span class="pos-badge">${p.position}</span>
      </div>
      <div class="player-tags">
        <span class="tag level">${levelEmoji} ${p.level}</span>
        ${speedTag}${staminaTag}${styles}${skills}
      </div>
      ${p.note ? `<div style="font-size:.78rem;color:var(--gray-400);margin-top:8px;">📝 ${p.note}</div>` : ''}
    </div>`;
}

// ── 오늘 경기 선수 토글 ───────────────────────────
function toggleSelect(id) {
  if (selectedIds.has(id)) selectedIds.delete(id);
  else selectedIds.add(id);
  renderMatchPlayers();
  hideAIResult();
}

function updateSelectedCount() {
  document.getElementById('selected-count').textContent = `${selectedIds.size}명 선택됨`;
}

function hideAIResult() {
  document.getElementById('ai-result').classList.add('hidden');
}

// ══════════════════════════════════════════════════
//  선수 추가 / 수정 모달
// ══════════════════════════════════════════════════
function openAddPlayerModal() {
  document.getElementById('modal-title').textContent = '선수 추가';
  document.getElementById('modal-player-id').value = '';
  document.getElementById('modal-name').value = '';
  document.getElementById('modal-number').value = '';
  document.getElementById('modal-speed').value = '보통';
  document.getElementById('modal-stamina').value = '보통';
  document.getElementById('modal-note').value = '';

  // 피커 초기화
  resetPicker('position-picker', 'pos-btn');
  resetPicker('style-picker', 'tag-btn');
  resetPicker('skill-picker', 'tag-btn');
  // 레벨 기본값 중급
  document.querySelectorAll('#level-picker .level-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.level === '중급');
  });

  document.getElementById('player-modal').classList.remove('hidden');
}

function openEditPlayerModal(id) {
  const p = players.find(x => x.id === id);
  if (!p) return;

  document.getElementById('modal-title').textContent = '선수 수정';
  document.getElementById('modal-player-id').value = p.id;
  document.getElementById('modal-name').value = p.name;
  document.getElementById('modal-number').value = p.number || '';
  document.getElementById('modal-speed').value = p.speed;
  document.getElementById('modal-stamina').value = p.stamina;
  document.getElementById('modal-note').value = p.note || '';

  // 포지션
  document.querySelectorAll('#position-picker .pos-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.pos === p.position);
  });
  // 레벨
  document.querySelectorAll('#level-picker .level-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.level === p.level);
  });
  // 성향
  document.querySelectorAll('#style-picker .tag-btn').forEach(b => {
    b.classList.toggle('active', (p.styles || []).includes(b.dataset.val));
  });
  // 특기
  document.querySelectorAll('#skill-picker .tag-btn').forEach(b => {
    b.classList.toggle('active', (p.skills || []).includes(b.dataset.val));
  });

  document.getElementById('player-modal').classList.remove('hidden');
}

function closePlayerModal() {
  document.getElementById('player-modal').classList.add('hidden');
}
function closeModalOnOverlay(e) {
  if (e.target === e.currentTarget) closePlayerModal();
}

function resetPicker(pickerId, btnClass) {
  document.querySelectorAll(`#${pickerId} .${btnClass}`).forEach(b => b.classList.remove('active'));
}

// 피커 버튼 클릭 핸들러 (단일 선택)
document.querySelectorAll('#position-picker .pos-btn, #level-picker .level-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    btn.closest('.position-picker, .level-picker').querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

// 태그 피커 (복수 선택)
document.querySelectorAll('#style-picker .tag-btn, #skill-picker .tag-btn').forEach(btn => {
  btn.addEventListener('click', () => btn.classList.toggle('active'));
});

function savePlayer() {
  const name = document.getElementById('modal-name').value.trim();
  if (!name) { alert('이름을 입력해주세요.'); return; }

  const posBtn = document.querySelector('#position-picker .pos-btn.active');
  if (!posBtn) { alert('포지션을 선택해주세요.'); return; }

  const levelBtn = document.querySelector('#level-picker .level-btn.active');

  const styles = [...document.querySelectorAll('#style-picker .tag-btn.active')].map(b => b.dataset.val);
  const skills = [...document.querySelectorAll('#skill-picker .tag-btn.active')].map(b => b.dataset.val);

  const playerData = {
    name,
    number: document.getElementById('modal-number').value || '',
    position: posBtn.dataset.pos,
    level: levelBtn ? levelBtn.dataset.level : '중급',
    speed: document.getElementById('modal-speed').value,
    stamina: document.getElementById('modal-stamina').value,
    styles,
    skills,
    note: document.getElementById('modal-note').value.trim(),
  };

  const editId = document.getElementById('modal-player-id').value;
  if (editId) {
    const idx = players.findIndex(p => p.id === editId);
    if (idx !== -1) players[idx] = { ...players[idx], ...playerData };
  } else {
    players.push({ id: generateId(), ...playerData });
  }

  saveToStorage();
  renderRoster();
  closePlayerModal();
}

function deletePlayer(id) {
  if (!confirm('이 선수를 삭제하시겠습니까?')) return;
  players = players.filter(p => p.id !== id);
  selectedIds.delete(id);
  saveToStorage();
  renderRoster();
}

// ══════════════════════════════════════════════════
//  Gemini AI 전술 추천
// ══════════════════════════════════════════════════
async function getTacticsFromAI() {
  const apiKey = getApiKey();
  if (!apiKey) {
    alert('설정 탭에서 Gemini API 키를 먼저 입력해주세요.');
    showPage('settings');
    return;
  }

  const selected = players.filter(p => selectedIds.has(p.id));
  if (selected.length < 5) {
    alert('최소 5명 이상의 선수를 선택해주세요.');
    return;
  }

  const style = document.getElementById('preferred-style').value;
  const opponentLevel = document.getElementById('opponent-level').value;

  showLoading(true);
  hideAIResult();

  const prompt = buildPrompt(selected, style, opponentLevel);

  try {
    const response = await callGemini(apiKey, prompt);
    const text = response?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) throw new Error('AI 응답이 비어있습니다.');

    const parsed = parseAIResponse(text, selected);
    renderAIResult(parsed);
  } catch (err) {
    alert('AI 호출 중 오류가 발생했습니다: ' + err.message);
    console.error(err);
  } finally {
    showLoading(false);
  }
}

function buildPrompt(selected, style, opponentLevel) {
  const playerDescs = selected.map((p, i) =>
    `${i + 1}. ${p.name} | 포지션선호: ${p.position} | 실력: ${p.level} | 스피드: ${p.speed} | 체력: ${p.stamina} | 성향: ${(p.styles || []).join(', ') || '없음'} | 특기: ${(p.skills || []).join(', ') || '없음'}`
  ).join('\n');

  return `당신은 아마추어 조기축구팀의 전술 코치입니다.
아래 선수 정보를 바탕으로 오늘 경기의 포메이션과 전술을 추천해주세요.

[오늘 경기 선수 목록 - 총 ${selected.length}명]
${playerDescs}

[감독 희망 스타일]: ${style}
[상대팀 수준]: ${opponentLevel}

다음 형식으로 정확히 JSON만 출력해주세요. 다른 텍스트는 절대 포함하지 마세요:

{
  "formation": "4-3-3",
  "formation_reason": "포메이션 선택 이유 (2-3문장, 아마추어 수준에 맞게)",
  "team_tactics": "팀 전체 전술 요약 (3-4문장, 아마추어가 이해하기 쉽게 구체적으로)",
  "key_points": ["핵심 전술 포인트 1", "핵심 전술 포인트 2", "핵심 전술 포인트 3"],
  "players": [
    {
      "name": "선수이름",
      "assigned_position": "배정 포지션 (예: 왼쪽 수비수)",
      "instructions": [
        "구체적인 움직임 지침 1 (아마추어 수준에서 실제로 할 수 있는 것)",
        "구체적인 움직임 지침 2",
        "구체적인 움직임 지침 3"
      ]
    }
  ]
}

주의사항:
- 선수 ${selected.length}명 모두 players 배열에 포함해야 합니다
- 아마추어 조기축구 수준에 맞춰 현실적이고 실행 가능한 지침을 주세요
- 전문 용어보다 쉬운 언어로 설명해주세요
- 각 선수의 특성(실력, 포지션 선호, 체력 등)을 반드시 반영해주세요`;
}

async function callGemini(apiKey, prompt) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`;
  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.7,
      maxOutputTokens: 4096,
    }
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    const errText = await res.text();
    let errMsg = `HTTP ${res.status}`;
    try {
      const errJson = JSON.parse(errText);
      errMsg = errJson?.error?.message || errMsg;
    } catch {}
    throw new Error(errMsg);
  }

  return res.json();
}

function parseAIResponse(text, selected) {
  // JSON 블록 추출 (```json ... ``` 또는 { ... } 형태)
  const jsonMatch = text.match(/```json\s*([\s\S]*?)```/) || text.match(/(\{[\s\S]*\})/);
  const jsonStr = jsonMatch ? jsonMatch[1].trim() : text.trim();

  try {
    const data = JSON.parse(jsonStr);
    // players 배열에 선수 정보 보강
    if (data.players) {
      data.players = data.players.map(pi => {
        const orig = selected.find(s => s.name === pi.name) || {};
        return { ...pi, position_badge: orig.position || pi.assigned_position };
      });
    }
    return data;
  } catch (e) {
    // 파싱 실패 시 원문 텍스트로 폴백
    return { raw: text };
  }
}

function renderAIResult(data) {
  const container = document.getElementById('ai-result-content');
  document.getElementById('ai-result').classList.remove('hidden');

  if (data.raw) {
    // 파싱 실패 폴백: 마크다운처럼 보여주기
    container.innerHTML = `<pre style="white-space:pre-wrap;font-size:.875rem;color:var(--gray-700)">${escHtml(data.raw)}</pre>`;
    return;
  }

  const keyPointsHTML = (data.key_points || [])
    .map(kp => `<li>${escHtml(kp)}</li>`).join('');

  const playersHTML = (data.players || []).map(pi => `
    <div class="player-instruction">
      <div class="pi-header">
        <span class="pi-name">${escHtml(pi.name)}</span>
        <span class="pi-pos">${escHtml(pi.assigned_position || '')}</span>
      </div>
      <ul class="pi-points">
        ${(pi.instructions || []).map(inst => `<li>${escHtml(inst)}</li>`).join('')}
      </ul>
    </div>`).join('');

  container.innerHTML = `
    <div class="formation-box">
      <div class="formation-name">${escHtml(data.formation || '?-?-?')}</div>
      <div class="formation-desc">${escHtml(data.formation_reason || '')}</div>
    </div>

    <div class="tactics-summary">
      <strong style="display:block;margin-bottom:6px;">📋 팀 전술 요약</strong>
      ${escHtml(data.team_tactics || '')}
      ${keyPointsHTML ? `<ul style="margin-top:10px;padding-left:18px;line-height:1.8">${keyPointsHTML}</ul>` : ''}
    </div>

    <div class="players-section">
      <h4>👤 선수별 개인 지침</h4>
      ${playersHTML}
    </div>`;

  // 결과로 스크롤
  document.getElementById('ai-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── 유틸 ──────────────────────────────────────────
function showLoading(show) {
  document.getElementById('loading-overlay').classList.toggle('hidden', !show);
}

function escHtml(str) {
  if (typeof str !== 'string') return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/\n/g, '<br>');
}

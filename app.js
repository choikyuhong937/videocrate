/* =============================================
   조기축구 감독실 — app.js
   ============================================= */

// ── 상태 ──────────────────────────────────────
let players = [];
let selectedIds = new Set();

// ── 초기화 ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadFromStorage();
  renderRoster();
  loadApiKeyStatus();
  initChipPickers();
});

// ── 페이지 전환 ───────────────────────────────
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.add('active');
  document.getElementById(`tab-${name}`).classList.add('active');
  if (name === 'match') renderMatchPlayers();
}

// ── 로컬 스토리지 ─────────────────────────────
function loadFromStorage() {
  try { players = JSON.parse(localStorage.getItem('soccer_players') || '[]'); }
  catch { players = []; }
}
function saveToStorage() {
  localStorage.setItem('soccer_players', JSON.stringify(players));
}
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 5); }

// ── API 키 ────────────────────────────────────
function saveApiKey() {
  const key = document.getElementById('api-key-input').value.trim();
  if (!key) { showApiStatus('API 키를 입력해주세요.', false); return; }
  localStorage.setItem('gemini_api_key', key);
  document.getElementById('api-key-input').value = '';
  showApiStatus('✅ 저장되었습니다.', true);
}
function loadApiKeyStatus() {
  if (localStorage.getItem('gemini_api_key')) showApiStatus('✅ API 키가 등록되어 있습니다.', true);
}
function showApiStatus(msg, ok) {
  const el = document.getElementById('api-key-status');
  el.textContent = msg;
  el.className = 'status-text ' + (ok ? 'ok' : 'err');
}
function getApiKey() { return localStorage.getItem('gemini_api_key') || ''; }

// ── 초기화 ────────────────────────────────────
function clearAllData() {
  if (!confirm('선수 명단을 모두 삭제할까요?')) return;
  players = [];
  selectedIds.clear();
  saveToStorage();
  renderRoster();
  renderMatchPlayers();
  showToast('초기화 완료');
}

// ── 공유 ──────────────────────────────────────
async function shareApp() {
  const url  = 'https://choikyuhong937.github.io/videocrate/';
  const text = '⚽ 조기축구 감독실 — 선수 등록하고 AI 전술 추천 받아봐요!';

  if (navigator.share) {
    try {
      await navigator.share({ title: '조기축구 감독실', text, url });
    } catch {}
    return;
  }
  // 공유 API 미지원 → 클립보드 복사
  try {
    await navigator.clipboard.writeText(url);
    showToast('링크가 복사되었습니다! 카톡에 붙여넣기 하세요 📋');
  } catch {
    prompt('아래 링크를 복사하세요:', url);
  }
}

async function shareResult() {
  const resultEl = document.getElementById('ai-result-content');
  const formation = resultEl.querySelector('.formation-name')?.textContent || '';
  const text = `⚽ 오늘 조기축구 전술\n포메이션: ${formation}\n\n감독실에서 AI 전술 받기 →\nhttps://choikyuhong937.github.io/videocrate/`;

  if (navigator.share) {
    try { await navigator.share({ title: '오늘 조기축구 전술', text }); return; } catch {}
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast('전술 결과가 복사되었습니다!');
  } catch {}
}

// ── 토스트 ────────────────────────────────────
let toastTimer;
function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 2400);
}

// ══════════════════════════════════════════════
//  렌더링
// ══════════════════════════════════════════════
function renderRoster() {
  const grid = document.getElementById('player-list');
  if (!players.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">👥</div>
        <p>선수가 없습니다</p>
        <button class="btn-primary" onclick="openAddPlayerModal()">첫 선수 추가하기</button>
      </div>`;
    return;
  }
  grid.innerHTML = players.map(p => cardHTML(p, false)).join('');
}

function renderMatchPlayers() {
  const grid = document.getElementById('match-player-list');
  if (!players.length) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><p>선수 명단 탭에서<br>선수를 먼저 추가해주세요</p></div>`;
    updateCount();
    return;
  }
  grid.innerHTML = players.map(p => cardHTML(p, true)).join('');
  updateCount();
}

function cardHTML(p, selectable) {
  const sel = selectable && selectedIds.has(p.id);
  const lvEmoji = { '초급': '🌱', '중급': '⚽', '고급': '🌟' }[p.level] || '';
  const skills = (p.skills || []).map(s => `<span class="tag g">${s}</span>`).join('');
  const styles = (p.styles || []).map(s => `<span class="tag">${s}</span>`).join('');
  const numBadge = p.number ? `<span class="player-num">${p.number}</span>` : '';

  const clickAttr = selectable ? `onclick="toggleSelect('${p.id}')"` : '';
  const check = selectable
    ? `<div class="check-circle">${sel ? '✓' : ''}</div>`
    : '';
  const actions = !selectable
    ? `<div class="card-actions">
         <button class="card-btn" onclick="openEditModal('${p.id}')">수정</button>
         <button class="card-btn" onclick="deletePlayer('${p.id}')">삭제</button>
       </div>`
    : '';

  return `
    <div class="player-card ${sel ? 'selected' : ''}" ${clickAttr}>
      ${check}
      ${numBadge}
      <div class="player-name-text">${escHtml(p.name)}</div>
      <span class="pos-badge">${Array.isArray(p.position) ? p.position.join('/') : p.position}</span>
      <div class="card-tags">
        <span class="tag">${lvEmoji} ${p.level}</span>
        ${p.speed !== '보통' ? `<span class="tag">${p.speed}</span>` : ''}
        ${styles}${skills}
      </div>
      ${actions}
    </div>`;
}

// ── 선수 선택 ─────────────────────────────────
function toggleSelect(id) {
  if (selectedIds.has(id)) selectedIds.delete(id);
  else selectedIds.add(id);
  renderMatchPlayers();
  document.getElementById('ai-result').classList.add('hidden');
}
function updateCount() {
  document.getElementById('selected-count').textContent = `${selectedIds.size}명`;
}

// ══════════════════════════════════════════════
//  모달: 선수 추가 / 수정
// ══════════════════════════════════════════════
function openAddPlayerModal() {
  document.getElementById('modal-title').textContent = '선수 추가';
  document.getElementById('modal-player-id').value = '';
  document.getElementById('modal-name').value = '';
  document.getElementById('modal-number').value = '';
  document.getElementById('modal-speed').value = '보통';
  document.getElementById('modal-stamina').value = '보통';
  document.getElementById('modal-note').value = '';
  resetChips('position-picker');
  resetChips('style-picker');
  resetChips('skill-picker');
  setChipActive('level-picker', '.level-chip', '중급', 'data-level');
  openModal();
}

function openEditModal(id) {
  const p = players.find(x => x.id === id);
  if (!p) return;
  document.getElementById('modal-title').textContent = '선수 수정';
  document.getElementById('modal-player-id').value = p.id;
  document.getElementById('modal-name').value = p.name;
  document.getElementById('modal-number').value = p.number || '';
  document.getElementById('modal-speed').value = p.speed;
  document.getElementById('modal-stamina').value = p.stamina;
  document.getElementById('modal-note').value = p.note || '';

  resetChips('position-picker');
  resetChips('style-picker');
  resetChips('skill-picker');
  resetChips('level-picker');

  // 포지션
  document.querySelectorAll('#position-picker .pos-chip').forEach(b => {
    const pos = Array.isArray(p.position) ? p.position : [p.position];
    if (pos.includes(b.dataset.pos)) b.classList.add('active');
  });
  // 레벨
  document.querySelectorAll('#level-picker .level-chip').forEach(b => {
    if (b.dataset.level === p.level) b.classList.add('active');
  });
  // 성향
  document.querySelectorAll('#style-picker .tag-chip').forEach(b => {
    if ((p.styles || []).includes(b.dataset.val)) b.classList.add('active');
  });
  // 특기
  document.querySelectorAll('#skill-picker .tag-chip').forEach(b => {
    if ((p.skills || []).includes(b.dataset.val)) b.classList.add('active');
  });

  openModal();
}

function openModal() {
  document.getElementById('player-modal').classList.remove('hidden');
  // 첫 입력란에 포커스 (살짝 딜레이)
  setTimeout(() => document.getElementById('modal-name').focus(), 250);
}

function closePlayerModal() {
  document.getElementById('player-modal').classList.add('hidden');
}

function savePlayer() {
  const name = document.getElementById('modal-name').value.trim();
  if (!name) { alert('이름을 입력해주세요.'); return; }

  const posEls = [...document.querySelectorAll('#position-picker .pos-chip.active')];
  if (!posEls.length) { alert('포지션을 선택해주세요.'); return; }

  const lvEl = document.querySelector('#level-picker .level-chip.active');
  const styles = [...document.querySelectorAll('#style-picker .tag-chip.active')].map(b => b.dataset.val);
  const skills = [...document.querySelectorAll('#skill-picker .tag-chip.active')].map(b => b.dataset.val);

  const data = {
    name,
    number: document.getElementById('modal-number').value || '',
    position: posEls.map(b => b.dataset.pos),
    level: lvEl ? lvEl.dataset.level : '중급',
    speed: document.getElementById('modal-speed').value,
    stamina: document.getElementById('modal-stamina').value,
    styles, skills,
    note: document.getElementById('modal-note').value.trim(),
  };

  const editId = document.getElementById('modal-player-id').value;
  if (editId) {
    const i = players.findIndex(p => p.id === editId);
    if (i !== -1) players[i] = { ...players[i], ...data };
  } else {
    players.push({ id: uid(), ...data });
  }

  saveToStorage();
  renderRoster();
  closePlayerModal();
  showToast(editId ? '선수 정보를 수정했습니다.' : `${name} 선수를 추가했습니다!`);
}

function deletePlayer(id) {
  const p = players.find(x => x.id === id);
  if (!p) return;
  if (!confirm(`${p.name} 선수를 삭제할까요?`)) return;
  players = players.filter(x => x.id !== id);
  selectedIds.delete(id);
  saveToStorage();
  renderRoster();
  showToast('삭제했습니다.');
}

// ── 칩 피커 초기화 ────────────────────────────
function initChipPickers() {
  // 포지션: 복수 선택
  document.querySelectorAll('#position-picker .pos-chip').forEach(btn => {
    btn.addEventListener('click', () => btn.classList.toggle('active'));
  });
  document.querySelectorAll('#level-picker .level-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#level-picker .level-chip').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });
  // 성향, 특기: 복수 선택
  document.querySelectorAll('#style-picker .tag-chip, #skill-picker .tag-chip').forEach(btn => {
    btn.addEventListener('click', () => btn.classList.toggle('active'));
  });
}

function resetChips(pickerId) {
  document.querySelectorAll(`#${pickerId} .chip`).forEach(b => b.classList.remove('active'));
}
function setChipActive(pickerId, selector, value, dataAttr) {
  document.querySelectorAll(`#${pickerId} ${selector}`).forEach(b => {
    if (b.dataset[dataAttr.replace('data-', '')] === value) b.classList.add('active');
  });
}

// ══════════════════════════════════════════════
//  AI 전술 추천 (Gemini)
// ══════════════════════════════════════════════
async function getTacticsFromAI() {
  if (!getApiKey()) {
    showToast('설정에서 API 키를 먼저 입력해주세요');
    setTimeout(() => showPage('settings'), 400);
    return;
  }
  const sel = players.filter(p => selectedIds.has(p.id));
  if (sel.length < 5) { showToast('최소 5명 이상 선택해주세요'); return; }

  const style     = document.getElementById('preferred-style').value;
  const opponent  = document.getElementById('opponent-level').value;

  showLoading(true);
  document.getElementById('ai-result').classList.add('hidden');

  try {
    const prompt   = buildPrompt(sel, style, opponent);
    const response = await callGemini(getApiKey(), prompt);
    const text     = response?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) throw new Error('AI 응답이 비어있습니다.');
    const parsed = parseAI(text, sel);
    renderResult(parsed);
  } catch (err) {
    showToast('오류: ' + err.message);
    console.error(err);
  } finally {
    showLoading(false);
  }
}

function buildPrompt(sel, style, opponent) {
  const lines = sel.map((p, i) =>
    `${i+1}. ${p.name} | 포지션: ${Array.isArray(p.position) ? p.position.join('/') : p.position} | 실력: ${p.level} | 스피드: ${p.speed} | 체력: ${p.stamina} | 성향: ${(p.styles||[]).join(',') || '없음'} | 특기: ${(p.skills||[]).join(',') || '없음'}`
  ).join('\n');

  return `당신은 아마추어 조기축구팀 전술 코치입니다.
아래 선수 정보로 오늘 경기 포메이션·전술·포지션 배치를 추천해주세요.

[출전 선수 ${sel.length}명]
${lines}

[감독 희망 스타일]: ${style}
[상대팀 수준]: ${opponent}

아래 JSON 형식으로만 출력하세요. 다른 텍스트 절대 금지:

{
  "formation": "4-3-3",
  "formation_reason": "포메이션 선택 이유 (2문장, 쉬운 표현)",
  "team_tactics": "팀 전체 전술 요약 (3~4문장, 아마추어가 이해하기 쉽게)",
  "attack_direction": "주 공격 방향 설명 (예: 오른쪽 측면 집중 공격, 중앙 돌파 위주 등)",
  "key_points": ["핵심 포인트 1", "핵심 포인트 2", "핵심 포인트 3"],
  "diagrams": [
    {
      "title": "기본 포메이션",
      "desc": "기본 배치 형태와 역할 요약 1~2문장",
      "players": [
        {"name":"선수이름","role":"GK","x":50,"y":92}
      ],
      "pass_routes": [
        {"from":"선수A","to":"선수B","desc":"빌드업 시작 패스"}
      ]
    },
    {
      "title": "공격 시 움직임",
      "desc": "공격 전환 시 형태 변화 2문장 (윙백 오버래핑 여부, 공격 루트 등)",
      "players": [
        {"name":"선수이름","role":"GK","x":50,"y":85}
      ],
      "arrows": [
        {"player":"선수이름","ex":85,"ey":25,"label":"오버래핑"}
      ],
      "pass_routes": [
        {"from":"선수A","to":"선수B","desc":"결정적 패스"}
      ]
    },
    {
      "title": "수비 시 대형",
      "desc": "수비 전환 시 라인 높이와 압박 방식 2문장",
      "players": [
        {"name":"선수이름","role":"GK","x":50,"y":95}
      ],
      "arrows": [
        {"player":"선수이름","ex":50,"ey":60,"label":"중앙 복귀"}
      ]
    }
  ],
  "players": [
    {
      "name": "선수이름",
      "assigned_position": "배정 포지션 예: 오른쪽 윙백",
      "pass_first": "1순위 패스 대상 선수 이름",
      "pass_second": "2순위 패스 대상 선수 이름",
      "instructions": [
        "이 선수의 특성에 맞는 구체적 지침 1",
        "이 선수의 특성에 맞는 구체적 지침 2",
        "이 선수의 특성에 맞는 구체적 지침 3",
        "이 선수의 특성에 맞는 구체적 지침 4"
      ]
    }
  ]
}

좌표 규칙:
- x: 0=왼쪽 터치라인, 50=중앙, 100=오른쪽 터치라인
- y: 0=상대 골대, 50=하프라인, 100=우리 골대
- GK: y=90~95, 수비수: y=72~82, 미드필더: y=45~60, 공격수: y=15~35
- arrows의 player는 해당 다이어그램 players의 name과 동일해야 함
- pass_routes의 from, to는 해당 다이어그램 players의 name과 동일해야 함

중요:
- 선수 ${sel.length}명 전원 diagrams 각 다이어그램과 players 배열에 포함
- diagrams는 정확히 3개 (기본, 공격, 수비)
- arrows는 공격/수비 다이어그램에서 핵심 이동 2~4개
- pass_routes는 각 다이어그램에서 주요 패스 연결 3~5개
- 각 선수의 pass_first, pass_second 반드시 포함 (패스 1순위, 2순위 대상)
- 각 선수의 instructions는 반드시 그 선수의 실력·체력·스피드·성향·특기를 반영하여 차별화
  예) 스피드 빠른 선수 → "공간이 보이면 전속력으로 전방 침투"
  예) 체력 약한 선수 → "전반에 집중하고 불필요한 달리기 줄이기"
  예) 수비적 성향 → "공격 시에도 뒷공간 항상 체크"
  예) 패스 특기 → "중앙에서 볼 받으면 ${sel[0]?.name || '공격수'}에게 스루패스 노리기"
- instructions에 패스 대상 선수 이름을 직접 언급 (예: "공 잡으면 먼저 홍길동 찾기")
- 아마추어 조기축구 수준에 맞는 현실적 지침
- 전문 용어 사용 금지, 쉬운 한국어로`;
}

async function callGemini(key, prompt) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${key}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.7, maxOutputTokens: 8192 }
    })
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json())?.error?.message || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function parseAI(text, sel) {
  const m = text.match(/```json\s*([\s\S]*?)```/) || text.match(/(\{[\s\S]*\})/);
  try {
    const d = JSON.parse(m ? m[1].trim() : text.trim());
    if (d.players) d.players = d.players.map(pi => ({
      ...pi,
      _orig: sel.find(s => s.name === pi.name) || {}
    }));
    return d;
  } catch {
    return { raw: text };
  }
}

function renderResult(d) {
  const box = document.getElementById('ai-result-content');
  document.getElementById('ai-result').classList.remove('hidden');

  if (d.raw) {
    box.innerHTML = `<pre style="white-space:pre-wrap;font-size:.82rem;color:var(--gray-700)">${escHtml(d.raw)}</pre>`;
    scrollToResult();
    return;
  }

  // 포메이션 박스 + 공격 방향
  const attackDir = d.attack_direction
    ? `<div class="attack-dir-badge">${escHtml(d.attack_direction)}</div>` : '';

  const formationBox = `
    <div class="formation-box">
      <div class="formation-name">${escHtml(d.formation || '?-?-?')}</div>
      <div class="formation-desc">${escHtml(d.formation_reason || '')}</div>
      ${attackDir}
    </div>`;

  // 피치 다이어그램
  let diagramsHTML = '';
  if (d.diagrams && d.diagrams.length) {
    diagramsHTML = `
      <div class="diagrams-section">
        <h4>📐 포메이션 다이어그램</h4>
        ${d.diagrams.map((dia, i) => renderPitch(dia, i)).join('')}
        <div class="diagram-legend">
          <span class="legend-item"><span class="legend-dot"></span> 선수 위치</span>
          <span class="legend-item"><span class="legend-dot gk"></span> 골키퍼</span>
          <span class="legend-item"><span class="legend-line move"></span> 이동</span>
          <span class="legend-item"><span class="legend-line pass"></span> 패스</span>
        </div>
      </div>`;
  }

  // 팀 전술
  const kpHTML = (d.key_points || []).map(kp => `<li>${escHtml(kp)}</li>`).join('');
  const tacticsBlock = `
    <div class="tactics-block">
      <strong>📋 팀 전술 요약</strong>
      ${escHtml(d.team_tactics || '')}
      ${kpHTML ? `<ul class="key-points">${kpHTML}</ul>` : ''}
    </div>`;

  // 선수별 지침 (패스 대상 포함)
  const piHTML = (d.players || []).map(pi => {
    const passInfo = [];
    if (pi.pass_first) passInfo.push(`1순위: ${escHtml(pi.pass_first)}`);
    if (pi.pass_second) passInfo.push(`2순위: ${escHtml(pi.pass_second)}`);
    const passBadge = passInfo.length
      ? `<div class="pi-pass"><span class="pi-pass-label">패스 대상</span> ${passInfo.join(' / ')}</div>` : '';

    return `
    <div class="pi-card">
      <div class="pi-head">
        <span class="pi-name">${escHtml(pi.name)}</span>
        <span class="pi-pos">${escHtml(pi.assigned_position || '')}</span>
      </div>
      ${passBadge}
      <ul class="pi-list">
        ${(pi.instructions || []).map(t => `<li>${escHtml(t)}</li>`).join('')}
      </ul>
    </div>`;
  }).join('');

  const playersSection = `
    <div class="players-section">
      <h4>👤 선수별 개인 지침</h4>
      ${piHTML}
    </div>`;

  box.innerHTML = formationBox + diagramsHTML + tacticsBlock + playersSection;
  scrollToResult();
}

// ── 피치 다이어그램 렌더링 ─────────────────────
function clamp(v, min, max) {
  return Math.max(min || 0, Math.min(max || 100, v || 50));
}

function renderPitch(diagram, idx) {
  // 선수 마커
  const playersHTML = (diagram.players || []).map(p => {
    const isGK = /GK/i.test(p.role || '');
    const ch = (p.name || '?')[0];
    const x = clamp(p.x, 5, 95);
    const y = clamp(p.y, 4, 96);
    return `<div class="pp" style="left:${x}%;top:${y}%">
      <div class="pp-dot${isGK ? ' gk' : ''}">${escHtml(ch)}</div>
      <div class="pp-label">${escHtml(p.name)}</div>
    </div>`;
  }).join('');

  // 이동 화살표 (노란 점선) + 패스 루트 (하늘색 실선)
  const moveArrows = diagram.arrows || [];
  const passRoutes = diagram.pass_routes || [];
  let svgContent = '';
  let arrowLabelsHTML = '';

  if (moveArrows.length || passRoutes.length) {
    const moveId = 'mv' + idx;
    const passId = 'ps' + idx;
    const players = diagram.players || [];

    // 이동 화살표
    const moveLines = moveArrows.map(a => {
      const from = players.find(p => p.name === a.player);
      if (!from) return '';
      const x1 = clamp(from.x, 5, 95) * 0.75;
      const y1 = clamp(from.y, 4, 96);
      const x2 = clamp(a.ex, 5, 95) * 0.75;
      const y2 = clamp(a.ey, 4, 96);
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
        stroke="#ffe066" stroke-width="1.2" stroke-dasharray="3,2"
        marker-end="url(#${moveId})" />`;
    }).join('');

    // 패스 루트
    const passLines = passRoutes.map(r => {
      const from = players.find(p => p.name === r.from);
      const to = players.find(p => p.name === r.to);
      if (!from || !to) return '';
      const x1 = clamp(from.x, 5, 95) * 0.75;
      const y1 = clamp(from.y, 4, 96);
      const x2 = clamp(to.x, 5, 95) * 0.75;
      const y2 = clamp(to.y, 4, 96);
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
        stroke="rgba(96,205,255,0.7)" stroke-width="0.9"
        marker-end="url(#${passId})" />`;
    }).join('');

    svgContent = `<svg class="pitch-arrows" viewBox="0 0 75 100">
      <defs>
        <marker id="${moveId}" markerWidth="5" markerHeight="4" refX="4.5" refY="2" orient="auto">
          <polygon points="0 0.3, 5 2, 0 3.7" fill="#ffe066"/>
        </marker>
        <marker id="${passId}" markerWidth="5" markerHeight="4" refX="4.5" refY="2" orient="auto">
          <polygon points="0 0.3, 5 2, 0 3.7" fill="rgba(96,205,255,0.9)"/>
        </marker>
      </defs>
      ${moveLines}${passLines}
    </svg>`;

    // 이동 라벨
    arrowLabelsHTML = moveArrows.map(a => {
      if (!a.label) return '';
      const ex = clamp(a.ex, 5, 95);
      const ey = clamp(a.ey, 4, 96);
      return `<div class="pitch-arrow-label" style="left:${ex}%;top:${ey}%">${escHtml(a.label)}</div>`;
    }).join('');
  }

  return `
    <div class="pitch-card">
      <div class="pitch-card-head">${escHtml(diagram.title)}</div>
      <div class="pitch-card-desc">${escHtml(diagram.desc || '')}</div>
      <div class="pitch">
        <div class="pitch-pa pitch-pa-t"></div>
        <div class="pitch-pa pitch-pa-b"></div>
        <div class="pitch-goal-label pitch-gl-t">상대 골대</div>
        <div class="pitch-goal-label pitch-gl-b">우리 골대</div>
        ${svgContent}
        ${playersHTML}
        ${arrowLabelsHTML}
      </div>
    </div>`;
}

function scrollToResult() {
  setTimeout(() => {
    document.getElementById('ai-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

// ── 유틸 ──────────────────────────────────────
function showLoading(v) {
  document.getElementById('loading-overlay').classList.toggle('hidden', !v);
}
function escHtml(s) {
  if (typeof s !== 'string') return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}

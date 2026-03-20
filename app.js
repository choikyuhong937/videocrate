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
  const text = `⚽ 오늘 조기축구 4경기 로테이션\n${formation}\n\n감독실에서 AI 전술 받기 →\nhttps://choikyuhong937.github.io/videocrate/`;

  if (navigator.share) {
    try { await navigator.share({ title: '오늘 조기축구 4경기 로테이션', text }); return; } catch {}
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

// 포지션 배열 반환 (구버전 단일 문자열 호환)
function getPositions(p) {
  if (Array.isArray(p.positions) && p.positions.length) return p.positions;
  if (p.position) return [p.position];
  return [];
}

function cardHTML(p, selectable) {
  const sel = selectable && selectedIds.has(p.id);
  const lvEmoji = { '초급': '🌱', '중급': '⚽', '고급': '🌟' }[p.level] || '';
  const skills = (p.skills || []).map(s => `<span class="tag g">${s}</span>`).join('');
  const styles = (p.styles || []).map(s => `<span class="tag">${s}</span>`).join('');
  const posBadges = getPositions(p).map(pos => `<span class="pos-badge">${pos}</span>`).join('');

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
      <div class="player-name-text">${escHtml(p.name)}</div>
      <div class="pos-badges">${posBadges}</div>
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
  document.getElementById('modal-speed').value = p.speed;
  document.getElementById('modal-stamina').value = p.stamina;
  document.getElementById('modal-note').value = p.note || '';

  resetChips('position-picker');
  resetChips('style-picker');
  resetChips('skill-picker');
  resetChips('level-picker');

  // 포지션 (복수 선택)
  const positions = getPositions(p);
  document.querySelectorAll('#position-picker .pos-chip').forEach(b => {
    if (positions.includes(b.dataset.pos)) b.classList.add('active');
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
  setTimeout(() => document.getElementById('modal-name').focus(), 250);
}

function closePlayerModal() {
  document.getElementById('player-modal').classList.add('hidden');
}

function savePlayer() {
  const name = document.getElementById('modal-name').value.trim();
  if (!name) { alert('이름을 입력해주세요.'); return; }

  const positions = [...document.querySelectorAll('#position-picker .pos-chip.active')].map(b => b.dataset.pos);
  if (!positions.length) { alert('포지션을 선택해주세요.'); return; }

  const lvEl = document.querySelector('#level-picker .level-chip.active');
  const styles = [...document.querySelectorAll('#style-picker .tag-chip.active')].map(b => b.dataset.val);
  const skills = [...document.querySelectorAll('#skill-picker .tag-chip.active')].map(b => b.dataset.val);

  const data = {
    name,
    positions,
    position: positions[0], // 하위 호환
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
  // 레벨: 단일 선택
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
//  AI 전술 추천 (Gemini) — 4경기 로테이션
// ══════════════════════════════════════════════
async function getTacticsFromAI() {
  if (!getApiKey()) {
    showToast('설정에서 API 키를 먼저 입력해주세요');
    setTimeout(() => showPage('settings'), 400);
    return;
  }
  const sel = players.filter(p => selectedIds.has(p.id));
  if (sel.length < 11) { showToast('최소 11명 이상 선택해주세요'); return; }

  const style    = document.getElementById('preferred-style').value;
  const opponent = document.getElementById('opponent-level').value;

  showLoading(true);
  document.getElementById('ai-result').classList.add('hidden');

  try {
    const prompt   = buildPrompt(sel, style, opponent);
    const response = await callGemini(getApiKey(), prompt);
    const text     = response?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) throw new Error('AI 응답이 비어있습니다.');
    const parsed = parseAI(text);
    renderResult(parsed);
  } catch (err) {
    showToast('오류: ' + err.message);
    console.error(err);
  } finally {
    showLoading(false);
  }
}

function buildPrompt(sel, style, opponent) {
  const total = sel.length;
  const subCount = total - 11;
  const lines = sel.map((p, i) => {
    const positions = getPositions(p).join('/');
    return `${i+1}. ${p.name} | 가능포지션: ${positions} | 실력: ${p.level} | 스피드: ${p.speed} | 체력: ${p.stamina} | 성향: ${(p.styles||[]).join(',') || '없음'} | 특기: ${(p.skills||[]).join(',') || '없음'}`;
  }).join('\n');

  return `당신은 아마추어 조기축구팀 전술 코치입니다.
오늘 총 4경기를 진행합니다. 전체 선수 ${total}명 중 매 경기 11명이 선발 출전하고 ${subCount}명은 교체 대기합니다.
모든 선수가 4경기에 걸쳐 최대한 공평하게 선발 출전 기회를 가지도록 로테이션을 구성해주세요.
각 선수의 가능한 포지션을 반드시 반영하여 포메이션을 짜주세요.

[전체 선수 ${total}명]
${lines}

[감독 희망 스타일]: ${style}
[상대팀 수준]: ${opponent}

아래 JSON 형식으로만 출력하세요. 다른 텍스트 절대 금지:

{
  "rotation_summary": "전체 로테이션 요약 (각 선수 선발 횟수 언급, 2~3문장)",
  "games": [
    {
      "game": 1,
      "formation": "4-3-3",
      "formation_reason": "포메이션 선택 이유 (1~2문장, 쉬운 표현)",
      "attack_direction": "주 공격 방향 (예: 오른쪽 측면 집중, 중앙 돌파 등)",
      "team_tactics": "팀 전체 전술 요약 (2~3문장, 아마추어가 이해하기 쉽게)",
      "key_points": ["핵심 포인트 1", "핵심 포인트 2", "핵심 포인트 3"],
      "diagram": {
        "players": [
          {"name":"선수이름","role":"GK","x":50,"y":92}
        ],
        "arrows": [
          {"player":"선수이름","ex":85,"ey":25,"label":"오버래핑"}
        ],
        "pass_routes": [
          {"from":"선수A","to":"선수B"}
        ]
      },
      "starters": [
        {
          "name": "선수이름",
          "assigned_position": "배정 포지션 (예: 오른쪽 윙백)",
          "pass_first": "1순위 패스 대상 선수 이름",
          "pass_second": "2순위 패스 대상 선수 이름",
          "instructions": [
            "이 선수의 특성에 맞는 구체적 움직임 지침 1",
            "이 선수의 특성에 맞는 구체적 움직임 지침 2",
            "이 선수의 특성에 맞는 구체적 움직임 지침 3"
          ]
        }
      ],
      "subs": ["교체선수1", "교체선수2"]
    }
  ]
}

좌표 규칙 (diagram.players):
- x: 0=왼쪽 터치라인, 50=중앙, 100=오른쪽 터치라인
- y: 0=상대 골대, 50=하프라인, 100=우리 골대
- GK: y=90~95, 수비수: y=72~82, 미드필더: y=45~60, 공격수: y=15~35
- arrows: 공격 시 핵심 이동 2~4개 (윙백 오버래핑, 전방 침투 등)
- pass_routes: 주요 패스 연결 3~5개 (from/to는 diagram.players의 name과 동일)

주의:
- 4경기 모두 포함 (game: 1, 2, 3, 4)
- 각 경기 starters 정확히 11명, diagram.players도 정확히 11명
- subs는 나머지 ${subCount}명 (이름만)
- 모든 선수 이름은 위 명단 그대로 사용
- 선수의 가능한 포지션 내에서 배정
- 각 선수의 pass_first, pass_second 반드시 포함
- 각 선수의 instructions는 반드시 그 선수의 실력·체력·스피드·성향·특기를 반영하여 차별화
  예) 스피드 빠른 선수 → "공간이 보이면 전속력으로 전방 침투"
  예) 체력 약한 선수 → "전반에 집중하고 불필요한 달리기 줄이기"
  예) 패스 특기 → "중앙에서 볼 받으면 공격수에게 스루패스 노리기"
- instructions에 패스 대상 선수 이름을 직접 언급 (예: "공 잡으면 먼저 홍길동 찾기")
- 아마추어 수준에 맞는 현실적 지침
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

function parseAI(text) {
  const m = text.match(/```json\s*([\s\S]*?)```/) || text.match(/(\{[\s\S]*\})/);
  try {
    return JSON.parse(m ? m[1].trim() : text.trim());
  } catch {
    return { raw: text };
  }
}

// ── 결과 렌더링: 4경기 탭 ─────────────────────
function renderResult(d) {
  const box = document.getElementById('ai-result-content');
  document.getElementById('ai-result').classList.remove('hidden');

  if (d.raw) {
    box.innerHTML = `<pre style="white-space:pre-wrap;font-size:.82rem;color:var(--gray-700)">${escHtml(d.raw)}</pre>`;
    scrollToResult();
    return;
  }

  const games = d.games || [];

  const summaryHTML = d.rotation_summary
    ? `<div class="rotation-summary"><strong>🔄 로테이션 요약</strong><p>${escHtml(d.rotation_summary)}</p></div>`
    : '';

  const tabBtns = games.map((g, i) =>
    `<button class="game-tab-btn ${i === 0 ? 'active' : ''}" onclick="switchGameTab(${i})">${g.game}경기</button>`
  ).join('');

  const panels = games.map((g, i) => {
    const kpHTML = (g.key_points || []).map(kp => `<li>${escHtml(kp)}</li>`).join('');

    // 공격 방향 뱃지
    const attackDir = g.attack_direction
      ? `<div class="attack-dir-badge">${escHtml(g.attack_direction)}</div>` : '';

    // 피치 다이어그램
    const diagramHTML = g.diagram ? renderPitch(g.diagram, i) : '';

    // 범례
    const legendHTML = g.diagram ? `
      <div class="diagram-legend">
        <span class="legend-item"><span class="legend-dot"></span> 선수</span>
        <span class="legend-item"><span class="legend-dot gk"></span> GK</span>
        <span class="legend-item"><span class="legend-line move"></span> 이동</span>
        <span class="legend-item"><span class="legend-line pass"></span> 패스</span>
      </div>` : '';

    // 선수별 지침 (패스 대상 포함)
    const startersHTML = (g.starters || []).map(pi => {
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

    const subsHTML = (g.subs || []).length
      ? `<div class="subs-box"><strong>🔄 교체 대기</strong><div class="subs-list">${(g.subs||[]).map(n=>`<span class="sub-chip">${escHtml(n)}</span>`).join('')}</div></div>`
      : '';

    return `
      <div class="game-panel ${i === 0 ? 'active' : ''}" id="game-panel-${i}">
        <div class="formation-box">
          <div class="formation-name">${escHtml(g.formation || '?-?-?')}</div>
          <div class="formation-desc">${escHtml(g.formation_reason || '')}</div>
          ${attackDir}
        </div>
        ${diagramHTML}
        ${legendHTML}
        <div class="tactics-block">
          <strong>📋 팀 전술</strong>
          ${escHtml(g.team_tactics || '')}
          ${kpHTML ? `<ul class="key-points">${kpHTML}</ul>` : ''}
        </div>
        ${subsHTML}
        <div class="players-section">
          <h4>👤 선발 11명 개인 지침</h4>
          ${startersHTML}
        </div>
      </div>`;
  }).join('');

  box.innerHTML = `
    ${summaryHTML}
    <div class="game-tabs">${tabBtns}</div>
    <div class="game-panels">${panels}</div>`;

  scrollToResult();
}

// ── 피치 다이어그램 렌더링 ─────────────────────
function clamp(v, min, max) {
  return Math.max(min || 0, Math.min(max || 100, v || 50));
}

function renderPitch(diagram, idx) {
  // 선수 마커
  const players = diagram.players || [];
  const playersHTML = players.map(p => {
    const isGK = /GK/i.test(p.role || '');
    const ch = (p.name || '?')[0];
    const x = clamp(p.x, 5, 95);
    const y = clamp(p.y, 4, 96);
    return `<div class="pp" style="left:${x}%;top:${y}%">
      <div class="pp-dot${isGK ? ' gk' : ''}">${escHtml(ch)}</div>
      <div class="pp-label">${escHtml(p.name)}</div>
    </div>`;
  }).join('');

  // 이동 화살표(노란 점선) + 패스 루트(하늘색 실선)
  const moveArrows = diagram.arrows || [];
  const passRoutes = diagram.pass_routes || [];
  let svgContent = '';
  let arrowLabelsHTML = '';

  if (moveArrows.length || passRoutes.length) {
    const moveId = 'mv' + idx;
    const passId = 'ps' + idx;

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
      ${passLines}${moveLines}
    </svg>`;

    arrowLabelsHTML = moveArrows.map(a => {
      if (!a.label) return '';
      const ex = clamp(a.ex, 5, 95);
      const ey = clamp(a.ey, 4, 96);
      return `<div class="pitch-arrow-label" style="left:${ex}%;top:${ey}%">${escHtml(a.label)}</div>`;
    }).join('');
  }

  return `
    <div class="pitch-card">
      <div class="pitch-card-head">📐 포메이션 배치도</div>
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

function switchGameTab(idx) {
  document.querySelectorAll('.game-tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
  document.querySelectorAll('.game-panel').forEach((p, i) => p.classList.toggle('active', i === idx));
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

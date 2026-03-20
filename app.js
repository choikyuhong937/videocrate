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
  // 포메이션: 단일 선택
  document.querySelectorAll('#formation-picker .fm-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#formation-picker .fm-chip').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
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
  const fmEl = document.querySelector('#formation-picker .fm-chip.active');
  const formation = fmEl ? fmEl.dataset.fm : 'AI추천';

  showLoading(true);
  document.getElementById('ai-result').classList.add('hidden');

  try {
    const prompt   = buildPrompt(sel, style, opponent, formation);
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

function buildPrompt(sel, style, opponent, formation) {
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

[선호 포메이션]: ${formation === 'AI추천' ? 'AI가 최적의 포메이션 자유롭게 추천' : formation + ' (4경기 모두 이 포메이션 사용)'}
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
        "lines": [
          ["공격수1","공격수2","공격수3"],
          ["미드필더1","미드필더2","미드필더3"],
          ["수비수1","수비수2","수비수3","수비수4"],
          ["GK이름"]
        ],
        "moves": [
          {"player":"선수이름","direction":"flank_right","label":"오버래핑"},
          {"player":"선수이름","direction":"forward","label":"침투"}
        ]
      },
      "starters": [
        {
          "name": "선수이름",
          "assigned_position": "배정 포지션 (예: 오른쪽 윙백)",
          "tactic": "이 경기 포메이션과 팀 전술 안에서 이 선수가 해야 할 핵심 역할 (1~2문장, 다른 선수 이름과 구체적 상황 명시)"
        }
      ],
      "subs": ["교체선수1", "교체선수2"]
    }
  ]
}

diagram 규칙:
- lines: 맨 앞 배열이 공격수, 맨 뒤 배열이 GK. 각 배열 안에서 왼쪽→오른쪽 순으로 이름만 나열
  예) 4-3-3: [["좌윙","CF","우윙"],["좌MF","중MF","우MF"],["좌수","좌CB","우CB","우수"],["GK"]]
- moves: 2~3개 핵심 움직임만. direction은 "flank_left"(왼쪽 측면돌파), "flank_right"(오른쪽 측면돌파), "forward"(전방침투) 셋 중 하나
- 선수 이름은 명단 그대로

주의:
- 4경기 모두 포함 (game: 1, 2, 3, 4)
- 각 경기 starters 정확히 11명, diagram.players도 정확히 11명
- subs는 나머지 ${subCount}명 (이름만)
- 모든 선수 이름은 위 명단 그대로 사용
- 선수의 가능한 포지션 내에서 배정
- 각 선수의 tactic은 반드시 아래 기준을 모두 충족:
  1) 이 경기의 포메이션/팀 전술과 직접 연결 (단순 개인 특성 나열 금지)
  2) 다른 선수 이름을 1명 이상 직접 언급 (패스 연결·공간 커버 등)
  3) 선수의 스피드·체력·성향·특기가 전술적 이유가 되어야 함
  4) 구체적 상황 묘사: "언제" "어디서" "어떻게" 포함
  좋은 예) "김철수가 오른쪽 오버래핑 나가면 그 빈 공간 즉시 메워서 역습 차단, 볼 따내면 박민준에게 짧게 패스"
  좋은 예) "스피드가 느리므로 박민준·이상훈과 삼각패스로 좁은 공간 뚫기, 단독 돌파보다 원터치 연계 우선"
  나쁜 예) "스피드가 빠르므로 전방 침투를 노린다" (너무 당연하고 팀 전술 연결 없음)
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
        <span class="legend-item"><span class="legend-line move"></span> 주요 움직임</span>
      </div>` : '';

    // 선수별 세부전술
    const startersHTML = (g.starters || []).map(pi => {
      return `
      <div class="pi-card">
        <div class="pi-head">
          <span class="pi-name">${escHtml(pi.name)}</span>
          <span class="pi-pos">${escHtml(pi.assigned_position || '')}</span>
        </div>
        <div class="pi-tactic">${escHtml(pi.tactic || '')}</div>
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
          <h4>🎯 선발 11명 세부전술</h4>
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

// lines[0]=공격수, lines[last]=GK → x,y 자동 계산
function calcPitchPositions(lines) {
  const n = lines.length;
  // Y 프리셋: 라인 수에 따라 상대 골대쪽(y=12)~우리 골대(y=90)
  const yPresets = {
    2: [20, 90],
    3: [20, 55, 90],
    4: [16, 48, 73, 90],
    5: [14, 36, 54, 73, 90],
    6: [12, 30, 45, 57, 73, 90],
  };
  const ys = yPresets[n] || lines.map((_, i) => Math.round(16 + 74 * i / (n - 1)));
  const result = [];
  lines.forEach((players, li) => {
    const y = ys[li];
    const m = players.length;
    players.forEach((name, pi) => {
      const x = m === 1 ? 50 : Math.round(12 + 76 * pi / (m - 1));
      result.push({ name, x, y, isGK: li === n - 1 });
    });
  });
  return result;
}

function renderPitch(diagram, idx) {
  const lines = diagram.lines || [];
  if (!lines.length) return '';

  const positions = calcPitchPositions(lines);
  const posMap = {};
  positions.forEach(p => { posMap[p.name] = p; });

  // 선수 마커
  const playersHTML = positions.map(p => {
    const ch = (p.name || '?')[0];
    return `<div class="pp" style="left:${p.x}%;top:${p.y}%">
      <div class="pp-dot${p.isGK ? ' gk' : ''}">${escHtml(ch)}</div>
      <div class="pp-label">${escHtml(p.name)}</div>
    </div>`;
  }).join('');

  // 이동 화살표
  const moves = diagram.moves || [];
  let svgLines = '';
  let labelHTML = '';

  if (moves.length) {
    const markerId = 'mv' + idx;
    svgLines = moves.map(m => {
      const p = posMap[m.player];
      if (!p) return '';
      const x1 = p.x, y1 = p.y;
      let x2, y2;
      if (m.direction === 'flank_left')  { x2 = Math.max(6, x1 - 18); y2 = Math.max(12, y1 - 22); }
      else if (m.direction === 'flank_right') { x2 = Math.min(94, x1 + 18); y2 = Math.max(12, y1 - 22); }
      else                               { x2 = x1; y2 = Math.max(10, y1 - 24); } // forward
      if (m.label) {
        labelHTML += `<div class="pitch-arrow-label" style="left:${x2}%;top:${y2}%">${escHtml(m.label)}</div>`;
      }
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
        stroke="#ffe066" stroke-width="1.4" stroke-dasharray="4,2.5"
        marker-end="url(#${markerId})" />`;
    }).join('');

    if (svgLines.trim()) {
      svgLines = `<svg class="pitch-arrows" viewBox="0 0 100 100" preserveAspectRatio="none">
        <defs>
          <marker id="${markerId}" markerWidth="5" markerHeight="4" refX="4.5" refY="2" orient="auto">
            <polygon points="0 0.3, 5 2, 0 3.7" fill="#ffe066"/>
          </marker>
        </defs>
        ${svgLines}
      </svg>`;
    }
  }

  return `
    <div class="pitch-card">
      <div class="pitch-card-head">📐 포메이션 배치도</div>
      <div class="pitch">
        <div class="pitch-pa pitch-pa-t"></div>
        <div class="pitch-pa pitch-pa-b"></div>
        <div class="pitch-goal-label pitch-gl-t">상대 골대</div>
        <div class="pitch-goal-label pitch-gl-b">우리 골대</div>
        ${svgLines}
        ${playersHTML}
        ${labelHTML}
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

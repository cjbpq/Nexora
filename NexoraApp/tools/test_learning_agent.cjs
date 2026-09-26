// Node >= 22.13. Exercise the production ETS API and navigation/session controllers with native adapters stubbed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { stripTypeScriptTypes } = require('node:module');
const { test } = require('node:test');
const root = path.resolve(__dirname, '../entry/src/main/ets');
const read = (relative) => fs.readFileSync(path.join(root, relative + '.ets'), 'utf8');

function load(source, names, bindings = {}) {
    const plain = source.replace(/^import\s[\s\S]*?;\r?\n/gm, '')
        .replace(/@(?:Component|Entry|ObjectLink|Prop|State|StorageProp|StorageLink|Watch|Link)(?:\([^)]*\))?\s*/g, '')
        .replace(/\bexport struct\b/g, 'class').replace(/^export\s/gm, '');
    return new Function(...Object.keys(bindings), stripTypeScriptTypes(plain, { mode: 'transform' }) +
        '\nreturn {' + names.join(',') + '};')(...Object.values(bindings));
}
function controller(relative, names, marker, bindings) {
    return load(read(relative).split(marker)[0] + '\n}', names, bindings);
}
// Extract complete real methods from MainChat/Index/EntryAbility, excluding ArkUI builders.
function methods(relative, className, names, bindings) {
    const source = read(relative);
    const blocks = names.map((name) => {
        const pattern = new RegExp('^\\s*(?:(?:private|public|protected|static|async)\\s+)*' + name + '\\s*\\(', 'm');
        const match = pattern.exec(source);
        assert.ok(match, 'missing production method ' + name);
        const start = match.index;
        const open = source.indexOf('{', start);
        let depth = 1, quote = '', lineComment = false, blockComment = false, escaped = false;
        for (let index = open + 1; index < source.length; index++) {
            const c = source[index], next = source[index + 1];
            if (lineComment) { if (c === '\n') lineComment = false; continue; }
            if (blockComment) { if (c === '*' && next === '/') { blockComment = false; index++; } continue; }
            if (quote) {
                if (escaped) { escaped = false; continue; }
                if (c === '\\') { escaped = true; continue; }
                if (c === quote) quote = '';
                continue;
            }
            if (c === '/' && next === '/') { lineComment = true; index++; continue; }
            if (c === '/' && next === '*') { blockComment = true; index++; continue; }
            if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
            if (c === '{') depth++;
            if (c === '}' && --depth === 0) return source.slice(start, index + 1);
            if (c !== '}') continue;
        }
        throw new Error('unbalanced production method ' + name);
    });
    return load('class ' + className + ' {\n' + blocks.join('\n') + '\n}', [className], bindings)[className];
}
function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}
async function settle() { for (let i = 0; i < 15; i++) await Promise.resolve(); }
function timers() {
    const pending = new Map(); let next = 1;
    return {
        pending,
        setTimeout: (callback, delay) => { const id = next++; pending.set(id, { callback, delay }); return id; },
        clearTimeout: (id) => pending.delete(id),
        async run() {
            const first = pending.entries().next().value;
            assert.ok(first, 'expected a scheduled refresh');
            pending.delete(first[0]); first[1].callback(); await settle();
        },
    };
}
function storage() {
    const values = new Map();
    return { values, get: (key) => values.get(key), setOrCreate: (key, value) => values.set(key, value) };
}
const target = (chapter = 0, book = 'book') => ({ lecture_id: 'lecture', lecture_title: 'Course', book_id: book,
    book_title: 'Book ' + book, chapter_index: chapter, chapter_name: 'Chapter ' + chapter, chapter_range: '100:50' });
const question = (id = 'q1') => ({ type: 'text', title: id, content: id, options: [], source_id: id,
    source: 'review', answer: 'reference', difficulty: '', hint: '' });
const hilog = { info() {}, warn() {}, error() {} };

function apiFixture() {
    const AppStorage = storage(); AppStorage.setOrCreate('nxSessionReady', true);
    let owner = { username: 'learner', serviceBase: 'https://learning.example', scope: 'one', revision: 1 };
    const calls = [];
    let transport = async () => ({ ok: true, message: '', status: 200, payload: { success: true, data: {}, next_actions: [] } });
    const http = { configured: true, captureIdentity: () => owner, isCurrent: (identity) => identity === owner,
        getJson: (route, identity) => { calls.push({ route, identity }); return transport(); },
        postJson: (route, payload, identity) => { calls.push({ route, payload, identity }); return transport(); },
    };
    const { Json } = load(read('common/JsonUtil'), ['Json']);
    const { LearningAgentApi } = load(read('common/LearningAgentApi'), ['LearningAgentApi'], { LearningHttp: http, Json, AppStorage });
    return { api: LearningAgentApi, AppStorage, calls, owner, http,
        setTransport: (fn) => { transport = fn; },
        switchIdentity: () => { owner = { ...owner, scope: 'two', revision: 2 }; },
    };
}

test('API keeps review attempts separate from flow submissions and sends encoded identifiers to real routes', async () => {
    const f = apiFixture(), t = target(), answers = [{ question_id: 'q1', answer: 'my answer' }];
    await f.api.reviewPlan(t);
    await f.api.getTask('task/one');
    await f.api.submitReview('quiz', 'attempt-1', t, answers);
    await f.api.getFlow('flow/one');
    await f.api.submitFlow('flow/one', answers);
    await f.api.openSession();
    await f.api.respondDecision('decision', 'accept');
    await f.api.getReport(t);
    await f.api.getGraph(t);
    assert.deepEqual(f.calls.map((call) => call.route), [
        '/api/agent/v1/review-plan', '/api/agent/v1/tasks/task%2Fone', '/api/agent/v1/review/submit',
        '/api/agent/v1/flow/state?flow_id=flow%2Fone', '/api/agent/v1/flow/submit',
        '/api/agent/v1/open-session', '/api/agent/v1/decision/respond',
        '/api/frontend/learning/report?lecture_id=lecture&book_id=book',
        '/api/frontend/knowledge-graph?lecture_id=lecture&book_id=book',
    ]);
    assert.equal(f.calls[2].payload.attempt_id, 'attempt-1');
    assert.equal(f.calls[2].payload.chapter_index, 0);
    assert.deepEqual(f.calls[4].payload, { flow_id: 'flow/one', answers });
    assert.ok(f.calls.every((call) => call.identity === f.owner));
});

test('API rejects work before login and late responses after account changes', async () => {
    const f = apiFixture();
    f.AppStorage.setOrCreate('nxSessionReady', false);
    await assert.rejects(f.api.openSession(), /登录/);
    assert.equal(f.calls.length, 0);
    f.AppStorage.setOrCreate('nxSessionReady', true);
    const pending = deferred(); f.setTransport(() => pending.promise);
    const request = f.api.getToday();
    f.switchIdentity();
    pending.resolve({ ok: true, message: '', status: 200, payload: { success: true, data: { status: 'resume' } } });
    await assert.rejects(request, /切换/);
});

function mainFixture() {
    const AppStorage = storage(), trace = [], http = { configured: false };
    const clock = timers();
    const MainChat = methods('pages/MainChat', 'MainChat', [
        'ensureLearningServices', 'loadLearningServices', 'consumeLaunchRoute', 'onLaunchRequested', 'openLearning', 'handleBackPress',
    ], { LearningHttp: http, AppStorage, hilog, DOMAIN: 0, TAG: '', ...clock,
        LearningSystemEntry: { prepare: () => trace.push('prepare') },
        LearningReadingApi: { flushReadingProgress: async () => trace.push('flush') },
    });
    const main = new MainChat();
    Object.assign(main, { attached: true, sessionReady: false, learningReady: null, launchConsuming: false,
        launchRequestVersion: 0, nxLaunchRoute: 'reader', nxLaunchDecision: 'decision-1', nxLaunchToken: 1,
        agentLaunchToken: 0, agentOpen: false, agentNavDepth: 0, learningOpen: false,
        mailOpen: true, notesOpen: true, showSheet: true, noteEditorOpen: true, viewerUrl: 'image',
        sidebarOpen: false, conversationId: '', getUIContext: () => ({ getHostContext: () => ({}) }),
        closeSidebar: () => trace.push('closeSidebar'), notify: (message) => trace.push(message),
    });
    main.app = { username: 'learner', loggedIn: true, learningEnabled: true, learningFrontendUrl: 'https://learning.example',
        refreshLearningRuntime: async () => { trace.push('runtime'); http.configured = true; } };
    return { main, trace, http, clock };
}

test('cold launch remains pending through login and Learning initialization, then consumes the latest route', async () => {
    const f = mainFixture(), m = f.main;
    await m.consumeLaunchRoute();
    assert.equal(m.nxLaunchRoute, 'reader'); assert.equal(f.trace.length, 0);
    m.sessionReady = true;
    const runtime = deferred();
    m.app.refreshLearningRuntime = async () => { f.trace.push('runtime'); await runtime.promise; f.http.configured = true; };
    const pending = m.consumeLaunchRoute(); await settle();
    assert.equal(m.agentOpen, false);
    m.nxLaunchRoute = 'review'; m.nxLaunchDecision = 'decision-2';
    runtime.resolve(); await pending;
    assert.equal(m.agentOpen, true); assert.equal(m.agentLaunchRoute, 'review');
    assert.equal(m.agentLaunchDecision, 'decision-2'); assert.equal(m.nxLaunchRoute, '');
    assert.equal(m.mailOpen || m.notesOpen || m.showSheet || m.learningOpen, false);
    assert.equal(m.viewerUrl, '');
    assert.equal(f.trace.filter((item) => item === 'prepare').length, 1);
    assert.equal(f.trace.filter((item) => item === 'flush').length, 1);
});

test('opening Learning flushes again; sign-out during initialization cannot consume a route', async () => {
    const f = mainFixture(), m = f.main; m.sessionReady = true;
    await m.ensureLearningServices(); m.agentOpen = true;
    await m.openLearning();
    assert.equal(m.learningOpen, true); assert.equal(m.agentOpen, false);
    assert.equal(f.trace.filter((item) => item === 'flush').length, 2);
    const runtime = deferred(); m.app.refreshLearningRuntime = () => runtime.promise;
    m.learningOpen = false; m.nxLaunchRoute = 'day';
    const pending = m.consumeLaunchRoute(); m.sessionReady = false; runtime.resolve(); await pending;
    assert.equal(m.agentOpen, false); assert.equal(m.nxLaunchRoute, 'day');
});

test('an explicit launch retry during failed runtime discovery is consumed once after the first attempt settles', async () => {
    const f = mainFixture(), m = f.main, first = deferred(); let requests = 0;
    m.sessionReady = true;
    m.app.refreshLearningRuntime = async () => {
        requests++;
        if (requests === 1) await first.promise;
        f.http.configured = requests > 1;
        m.app.learningEnabled = requests > 1;
    };
    const initial = m.consumeLaunchRoute();
    await settle();
    m.nxLaunchToken++;
    m.nxLaunchRoute = 'review';
    m.onLaunchRequested();
    await f.clock.run(); // the newer request encounters launchConsuming=true
    assert.equal(requests, 1);
    first.resolve(); await initial;
    assert.equal(m.agentOpen, false);
    await f.clock.run();
    assert.equal(requests, 2);
    assert.equal(m.agentOpen, true);
    assert.equal(m.agentLaunchRoute, 'review');
    assert.equal(f.clock.pending.size, 0);
});

test('failed launch requests with unchanged tokens never retry themselves', async () => {
    const f = mainFixture(), m = f.main, first = deferred(); let requests = 0;
    m.sessionReady = true;
    m.app.refreshLearningRuntime = async () => {
        requests++;
        if (requests === 1) await first.promise;
        f.http.configured = false;
        m.app.learningEnabled = false;
    };
    const initial = m.consumeLaunchRoute();
    m.nxLaunchToken++; m.onLaunchRequested(); await f.clock.run();
    first.resolve(); await initial; await f.clock.run();
    assert.equal(requests, 2); assert.equal(m.agentOpen, false);
    assert.equal(m.nxLaunchRoute, 'reader'); assert.equal(f.clock.pending.size, 0);
});

test('Index only publishes session readiness after validation and revokes system entry before logout awaits', async () => {
    const AppStorage = storage(), calls = [];
    const Index = methods('pages/Index', 'Index', ['bootstrap', 'enterHome', 'handleSignOut'], {
        AppStorage, chatStream: { isStreaming: false }, LearningSystemEntry: { clear: () => calls.push('clear') },
    });
    const index = new Index(), validation = deferred(), logout = deferred();
    index.getUIContext = () => ({ getHostContext: () => ({}) });
    index.app = { restore: async () => {}, validateSession: () => validation.promise,
        signOut: async () => { calls.push('logout'); await logout.promise; } };
    AppStorage.setOrCreate('nxLaunchRoute', 'review');
    const bootstrap = index.bootstrap(); await settle();
    assert.equal(AppStorage.get('nxSessionReady'), false);
    validation.resolve(true); await bootstrap;
    assert.equal(index.ready, true); assert.equal(AppStorage.get('nxSessionReady'), true);
    assert.equal(AppStorage.get('nxLaunchRoute'), 'review');
    const pending = index.handleSignOut();
    assert.equal(AppStorage.get('nxSessionReady'), false);
    assert.deepEqual(calls, ['clear', 'logout']);
    logout.resolve(); await pending; assert.equal(index.loggedIn, false);
});

test('EntryAbility remembers supported deep links, accepts repeated taps, and emits foreground transitions', () => {
    const AppStorage = storage();
    const EntryAbility = methods('entryability/EntryAbility', 'EntryAbility', [
        'rememberLaunchTarget', 'onNewWant', 'onForeground', 'onBackground',
    ], { AppStorage, hilog, DOMAIN: 0, LiveViewController: { shared: { stop() {}, startGenerating() {} } }, chatStream: { isStreaming: false } });
    const ability = new EntryAbility();
    ability.onNewWant({ parameters: { nx_route: 'review', decision_id: 'd1' } }, {});
    ability.onNewWant({ parameters: { nx_route: 'review', decision_id: 'd1' } }, {});
    assert.equal(AppStorage.get('nxLaunchToken'), 2);
    assert.equal(AppStorage.get('nxLaunchDecision'), 'd1');
    ability.onNewWant({ parameters: { nx_route: 'not-a-route' } }, {});
    assert.equal(AppStorage.get('nxLaunchToken'), 2);
    ability.onForeground(); assert.equal(AppStorage.get('appForeground'), true);
    ability.onBackground(); assert.equal(AppStorage.get('appForeground'), false);
});

function agentFixture() {
    const clock = timers(), AppStorage = storage(), requests = [], forms = [];
    const owner = {}, http = { captureIdentity: () => owner, isCurrent: (candidate) => candidate === owner };
    let event = null;
    const api = { getToday: async () => ({ status: 'resume', focus: target(), today: { study_minutes: 5, completed_chapters: 1 } }),
        getEvents: async () => [], openSession: async () => ({ target: target() }),
        getFlow: async (flowId) => ({ flow_id: flowId, status: 'running', step: 'opened', target: target() }) };
    const learning = { shared: { resolveReaderTarget: async (lecture, book) => {
        requests.push({ lecture, book });
        return { success: true, book: { id: book, title: book }, chapters: [0, 1, 2].map((index) => ({ index })) };
    } } };
    const { LearningAgent, AgentLevel } = controller('components/agent/LearningAgent', ['LearningAgent', 'AgentLevel'], '\n    @Builder', {
        NO_AGENT_TARGET: target(), NO_BOOK: {}, ListScroller: class { scrollToIndex() {} },
        LearningHttp: http, LearningAgentApi: api, LearningApi: learning, AppStorage, ...clock,
        LearningBridge: { latest: () => event }, LearningSystemEntry: { updateToday: async (...args) => forms.push(args) },
        agentFailure: (error) => error.message,
    });
    const agent = new LearningAgent(); agent.alive = true;
    agent.getUIContext = () => ({ getHostContext: () => ({}) });
    return { agent, api, learning, clock, requests, forms, AgentLevel, emit: (value) => { event = value; agent.onBridgeChanged(); } };
}

test('agent reader stack owns return and closes reader overlays before popping its frame', async () => {
    const f = agentFixture(), a = f.agent;
    await a.openReader(target(1), 'flow-1');
    assert.equal(a.top().level, f.AgentLevel.READER); assert.equal(a.top().flowId, 'flow-1'); assert.equal(a.navDepth, 1);
    const readerFrame = a.top(); assert.equal(a.active(readerFrame), true);
    a.readerOverlayOpen = true; a.navDepth = 0; a.onNavDepthBack();
    assert.equal(a.frames.length, 2); assert.equal(a.readerBackToken, 1); assert.equal(a.navDepth, 1);
    a.readerOverlayOpen = false; a.navDepth = 0; a.onNavDepthBack();
    assert.equal(a.top().level, f.AgentLevel.DAY); assert.equal(a.navDepth, 0);
    f.emit({ type: 'flow_reading_done', flowId: 'flow-1' });
    assert.equal(a.top().level, f.AgentLevel.REVIEW); assert.equal(a.top().flowId, 'flow-1');
});

test('late reader resolution cannot reopen after return, and a new route ignores an old flow completion', async () => {
    const f = agentFixture(), a = f.agent, pending = deferred();
    f.learning.shared.resolveReaderTarget = () => pending.promise;
    const opening = a.openReader(target(), 'old-flow'); a.goBack();
    pending.resolve({ success: true, book: { id: 'book' }, chapters: [{ index: 0 }] }); await opening;
    assert.equal(a.frames.length, 1);
    a.expectedFlowId = 'old-flow'; a.launchRoute = 'day';
    await a.dispatchRoute(a.launchVersion);
    f.emit({ type: 'flow_reading_done', flowId: 'old-flow' });
    assert.equal(a.frames.length, 1);
});

test('plan and prerequisite cards open their own targets; report/review remain in the same stack', async () => {
    const f = agentFixture(), a = f.agent;
    a.openCard({ card: { type: 'plan', target: target(2, 'planned') } }); await settle();
    assert.equal(a.top().target.book_id, 'planned'); assert.equal(a.top().target.chapter_index, 2);
    a.goBack();
    a.openCard({ card: { type: 'prereq', fromLectureId: 'prereq-lecture', fromBookId: 'prereq-book', fromChapterIndex: 1 } }); await settle();
    assert.equal(a.top().target.book_id, 'prereq-book'); assert.equal(a.top().target.chapter_index, 1);
    a.goBack(); await a.openReport(target());
    const report = a.top(); a.openReview(target(1));
    assert.equal(a.frames.length, 3); a.goBack(); assert.equal(a.top(), report);
});

test('decision deep links fetch their own record while today/bridge refreshes are still pending', async () => {
    const f = agentFixture(), a = f.agent, pending = deferred();
    const decision = { id: 'wanted', kind: 'agent_act', text: 'Specific decision', ts: 1 };
    f.api.getToday = () => pending.promise;
    f.api.getEvents = async () => [decision];
    const ordinaryRefresh = a.refresh();
    f.emit({ type: 'reading_synced', flowId: '' });
    a.launchRoute = 'judgment'; a.launchDecision = 'wanted';
    const routed = a.dispatchRoute(a.launchVersion);
    await settle();
    assert.equal(a.top().level, f.AgentLevel.INSPECT);
    assert.equal(a.top().entry.id, 'wanted');
    pending.resolve({ status: 'resume', focus: target(), today: { study_minutes: 5, completed_chapters: 1 } });
    await ordinaryRefresh; await routed;
    assert.equal(a.top().entry.id, 'wanted');
});

test('a manual navigation cancels the in-flight decision drawer without affecting flow polling', async () => {
    const f = agentFixture(), a = f.agent, pending = deferred();
    f.api.getEvents = () => pending.promise;
    a.launchRoute = 'mirror'; a.launchDecision = 'wanted';
    const routed = a.dispatchRoute(a.launchVersion);
    a.openReview(target(), 'flow-2');
    pending.resolve([{ id: 'wanted', kind: 'agent_act', text: 'Old request', ts: 1 }]); await routed;
    assert.equal(a.top().level, f.AgentLevel.REVIEW);
    assert.equal(a.top().flowId, 'flow-2');
});

function reviewFixture(flowId = 'flow-1') {
    const clock = timers(), AppStorage = storage(); let event = null;
    const api = { getFlow: async () => ({ status: 'running', step: 'opened', target: target() }) };
    const { LearningAgentReview } = controller('components/agent/LearningAgentReview', ['LearningAgentReview'], '\n    build() {', {
        NO_AGENT_TARGET: target(), LearningAgentApi: api, LearningApi: { shared: {} }, AppStorage, ...clock,
        LearningBridge: { latest: () => event }, agentFailure: (error) => error.message,
    });
    const review = new LearningAgentReview(); Object.assign(review, { alive: true, visible: true, flowId });
    return { review, api, clock, emit: () => { event = { type: 'flow_reading_done', flowId }; review.onBridgeChanged(); } };
}

test('flow completion arriving during the old opened response forces a second load and exposes the quiz', async () => {
    const f = reviewFixture(), r = f.review, first = deferred(); let calls = 0;
    f.api.getFlow = async () => ++calls === 1 ? first.promise : ({ status: 'running', step: 'quiz_generated', target: target(),
        quiz: { status: 'completed', questions: [question()] } });
    const pending = r.loadFlow(); f.emit();
    first.resolve({ status: 'running', step: 'opened', target: target() }); await pending;
    assert.equal(r.questions.length, 0);
    assert.equal([...f.clock.pending.values()][0].delay, 0);
    await f.clock.run();
    assert.equal(calls, 2); assert.equal(r.questions.length, 1); assert.equal(r.needsReading, false);
});

test('flow polling pauses under the reader and refreshes on return without erasing existing drafts', async () => {
    const f = reviewFixture(), r = f.review;
    f.api.getFlow = async () => ({ status: 'running', step: 'reading_done', target: target(), quiz: { status: 'queued', questions: [] } });
    await r.loadFlow(); assert.equal(f.clock.pending.size, 1);
    r.visible = false; r.onVisibleChanged(); assert.equal(f.clock.pending.size, 0);
    r.replaceQuestions([question('q1'), question('q2')]); r.answers = ['first', 'second'];
    f.api.getFlow = async () => ({ status: 'running', step: 'quiz_generated', target: target(),
        quiz: { status: 'completed', questions: [question('q2'), question('q1')] } });
    r.visible = true; r.onVisibleChanged(); await settle();
    assert.deepEqual(r.answers, ['second', 'first']); assert.equal(r.generating, false);
});

test('review submissions retain frozen target and attempt across retry, then isolate the next attempt', async () => {
    const f = reviewFixture(''), r = f.review, submitted = []; let attempt = 1, fail = true;
    r.selected = target(1, 'source');
    f.api.reviewPlan = async () => ({ task: { task_id: 'task-' + attempt, status: 'completed', result: {
        ...target(1, 'source'), quiz_id: 'same-quiz', attempt_id: 'attempt-' + attempt, questions: [question()]
    } } });
    f.api.submitReview = async (quizId, attemptId, origin, answers) => {
        submitted.push({ quizId, attemptId, origin, answers });
        if (fail) throw new Error('offline');
        return { score: '1/1', items: [{ question_id: 'q1', duplicate: false }] };
    };
    await r.startReview(); r.selected = target(2, 'different-book'); r.answers = ['answer'];
    await r.submit(); assert.equal(r.submitted, false); assert.deepEqual(r.answers, ['answer']);
    fail = false; await r.submit();
    assert.equal(submitted[1].origin.book_id, 'source'); assert.equal(submitted[1].origin.chapter_index, 1);
    assert.deepEqual(submitted[0], submitted[1]); assert.equal(r.submitted, true);
    attempt = 2; await r.startReview(); r.answers = ['new answer']; await r.submit();
    assert.equal(submitted[2].quizId, 'same-quiz'); assert.equal(submitted[2].attemptId, 'attempt-2');
});

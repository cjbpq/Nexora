import { AppState } from '../../common/AppState';
import { LearningApi, LearningBook, LearningChapterSummary, NO_BOOK } from '../../common/LearningApi';
import { LearningAgentApi, agentFailure, NO_AGENT_TARGET } from '../../common/LearningAgentApi';
import { LearningBridge } from '../../common/LearningBridge';
import { LearningSystemEntry } from '../../common/LearningSystemEntry';
import { LearningHttp } from '../../common/LearningHttp';
import {
    AgentEnvelope, TodayData, LearnTarget, TimelineEntry, PlanCard, PrereqCard, QuizCard,
    PrepCard, ProactiveCard, WrapupCard, CitationCard, FlowStateData
} from '../../common/LearningAgentModels';
import { LearningReader } from '../learning/LearningReader';
import { LearningAgentReview } from './LearningAgentReview';
import { LearningAgentReport } from './LearningAgentReport';
import { LearningAgentInspect } from './LearningAgentInspect';
import { MarkdownView } from '../chat/MarkdownBlock';

enum AgentLevel { DAY, READER, REVIEW, REPORT, INSPECT }

class AgentFrame {
    id: number = 0;
    level: AgentLevel = AgentLevel.DAY;
    target: LearnTarget = NO_AGENT_TARGET;
    flowId: string = '';
    book: LearningBook = NO_BOOK;
    chapters: LearningChapterSummary[] = [];
    entry: TimelineEntry | null = null;
}

@Component
export struct LearningAgent {
    @ObjectLink app: AppState;
    @Link @Watch('onNavDepthBack') navDepth: number;
    @Prop visible: boolean = true;
    @Prop launchRoute: string = 'day';
    @Prop launchDecision: string = '';
    @Prop @Watch('onLaunchChanged') launchToken: number = 0;
    @StorageProp('nxLearningBridgeTick') @Watch('onBridgeChanged') private bridgeTick: number = 0;
    onBack: () => void = () => {};
    onOpenLearning: () => void = () => {};
    onOpenImage: (url: string) => void = () => {};
    @State private frames: AgentFrame[] = [new AgentFrame()];
    @State private readerOverlayOpen: boolean = false;
    @State private readerBackToken: number = 0;
    @State private entries: TimelineEntry[] = [];
    @State private focus: LearnTarget = NO_AGENT_TARGET;
    @State private todayText: string = '正在同步今天的学习记录…';
    @State private errorText: string = '';
    @State private loading: boolean = true;
    @State private opening: boolean = false;
    @State private actionBusy: string = '';
    @State private draft: string = '';
    @State private sending: boolean = false;
    private alive: boolean = false;
    private nextId: number = 1;
    private refreshVersion: number = 0;
    private navigationVersion: number = 0;
    private launchVersion: number = 0;
    private pendingFlowId: string = '';
    private expectedFlowId: string = '';
    private scroller: ListScroller = new ListScroller();

    aboutToAppear(): void {
        this.alive = true;
        this.navDepth = 0;
        void this.refresh();
        this.onLaunchChanged();
    }

    aboutToDisappear(): void {
        this.alive = false;
        this.refreshVersion++;
        this.navigationVersion++;
        this.launchVersion++;
    }

    private top(): AgentFrame {
        return this.frames[this.frames.length - 1];
    }

    private active(frame: AgentFrame): boolean {
        return this.visible && this.top().id === frame.id;
    }

    private push(frame: AgentFrame): void {
        frame.id = this.nextId++;
        this.frames = this.frames.concat([frame]);
        this.navDepth = this.frames.length - 1;
    }

    private onNavDepthBack(): void {
        if (this.navDepth === this.frames.length - 1) {
            return;
        }
        if (this.top().level === AgentLevel.READER && this.readerOverlayOpen) {
            this.readerBackToken++;
            this.navDepth = this.frames.length - 1;
            return;
        }
        this.goBack();
    }

    private goBack(): void {
        this.navigationVersion++;
        this.opening = false;
        if (this.frames.length <= 1) {
            this.onBack();
            return;
        }
        this.frames = this.frames.slice(0, this.frames.length - 1);
        this.navDepth = this.frames.length - 1;
        this.readerOverlayOpen = false;
        if (this.top().level === AgentLevel.DAY) {
            void this.refresh();
        }
        this.continueFlow();
    }

    private onBridgeChanged(): void {
        if (!this.alive) {
            return;
        }
        void this.refresh();
        const event = LearningBridge.latest();
        if (event !== null && event.type === 'flow_reading_done' && event.flowId.length > 0 && event.flowId === this.expectedFlowId) {
            this.pendingFlowId = event.flowId;
            this.continueFlow();
        }
    }

    private continueFlow(): void {
        if (this.pendingFlowId.length === 0 || this.top().level === AgentLevel.READER) {
            return;
        }
        const flowId: string = this.pendingFlowId;
        this.pendingFlowId = '';
        this.expectedFlowId = '';
        if (this.top().level === AgentLevel.REVIEW && this.top().flowId === flowId) {
            return;
        }
        this.openReview(this.focus, flowId);
    }

    private onLaunchChanged(): void {
        const version: number = ++this.launchVersion;
        setTimeout(() => {
            if (this.alive && version === this.launchVersion) {
                void this.dispatchRoute(version);
            }
        }, 0);
    }

    private async dispatchRoute(version: number): Promise<void> {
        const navigationVersion: number = ++this.navigationVersion;
        this.frames = [new AgentFrame()];
        this.navDepth = 0;
        this.readerOverlayOpen = false;
        this.pendingFlowId = '';
        this.expectedFlowId = '';
        const route: string = this.launchRoute;
        const decisionId: string = this.launchDecision;
        if (route === 'study' || route === 'reader') {
            void this.openSession();
        } else if (route === 'review') {
            this.openReview(this.focus);
        } else if ((route === 'mirror' || route === 'judgment') && decisionId.length === 0) {
            this.openInspect(null);
        } else if (decisionId.length > 0) {
            // A bridge refresh can supersede refresh(); a deep link needs its own exact decision snapshot.
            try {
                const entries: TimelineEntry[] = await LearningAgentApi.getEvents();
                if (!this.alive || version !== this.launchVersion || navigationVersion !== this.navigationVersion) {
                    return;
                }
                const index: number = entries.findIndex((entry: TimelineEntry): boolean => entry.id === decisionId);
                if (route === 'mirror' || route === 'judgment') {
                    this.openInspect(index >= 0 ? entries[index] : null);
                    return;
                }
                this.entries = entries;
                if (index >= 0) {
                    setTimeout(() => {
                        if (this.alive && version === this.launchVersion && navigationVersion === this.navigationVersion &&
                            this.top().level === AgentLevel.DAY) {
                            this.scroller.scrollToIndex(index, false, ScrollAlign.CENTER);
                        }
                    }, 50);
                } else {
                    this.errorText = '这条决策已不在最近的学习记录中';
                }
            } catch (error) {
                if (this.alive && version === this.launchVersion && navigationVersion === this.navigationVersion) {
                    this.errorText = agentFailure(error);
                }
            }
        }
    }

    private async refresh(): Promise<void> {
        const version: number = ++this.refreshVersion;
        const owner = LearningHttp.captureIdentity();
        this.loading = true;
        try {
            const today: TodayData = await LearningAgentApi.getToday();
            if (!this.alive || version !== this.refreshVersion || !LearningHttp.isCurrent(owner)) {
                return;
            }
            this.focus = today.focus || NO_AGENT_TARGET;
            if (today.status === 'needs_course') {
                this.todayText = '先去学习选择课程，我会从阅读记录开始安排复习。';
            } else {
                this.todayText = this.focus.chapter_name.length > 0
                    ? (today.status === 'resume' ? '接着读：' : '今天的目标：') + this.focus.chapter_name : '今天还没有安排新的目标。';
                if (today.today !== undefined) {
                    this.todayText += '\n已学 ' + today.today.study_minutes + ' 分钟 · 已读完 ' + today.today.completed_chapters + ' 章';
                }
            }
            const entries: TimelineEntry[] = await LearningAgentApi.getEvents();
            if (this.alive && version === this.refreshVersion && LearningHttp.isCurrent(owner)) {
                this.entries = entries;
                this.errorText = '';
                const host = this.getUIContext().getHostContext();
                if (host !== undefined) {
                    void LearningSystemEntry.updateToday(host, today, entries);
                }
            }
        } catch (error) {
            if (this.alive && version === this.refreshVersion) {
                this.errorText = agentFailure(error);
            }
        } finally {
            if (this.alive && version === this.refreshVersion) {
                this.loading = false;
            }
        }
    }

    private async defaultTarget(preferred: LearnTarget = this.focus): Promise<LearnTarget> {
        if (preferred.lecture_id.length > 0 && preferred.book_id.length > 0) {
            return preferred;
        }
        const context = await LearningAgentApi.getContext();
        for (const lecture of context.lectures) {
            if (preferred.lecture_id.length > 0 && lecture.id !== preferred.lecture_id) {
                continue;
            }
            if (lecture.books.length > 0) {
                const book = lecture.books[0];
                return { lecture_id: lecture.id, lecture_title: lecture.title,
                    book_id: book.id, book_title: book.title, chapter_index: Math.max(0, preferred.chapter_index),
                    chapter_name: preferred.chapter_name, chapter_range: '' };
            }
        }
        throw new Error('还没有可用教材，请先去学习选择课程');
    }

    private async openSession(): Promise<void> {
        if (this.opening) {
            return;
        }
        const version: number = ++this.navigationVersion;
        this.opening = true;
        this.errorText = '';
        try {
            const session = await LearningAgentApi.openSession();
            if (this.alive && version === this.navigationVersion) {
                this.opening = false;
                await this.openReader(session.target);
            }
        } catch (error) {
            if (this.alive && version === this.navigationVersion) {
                this.opening = false;
                this.errorText = agentFailure(error);
            }
        }
    }

    private async openReader(target: LearnTarget, flowId: string = ''): Promise<void> {
        const version: number = ++this.navigationVersion;
        const owner = LearningHttp.captureIdentity();
        this.opening = true;
        this.errorText = '';
        try {
            const resolved = await LearningApi.shared.resolveReaderTarget(target.lecture_id, target.book_id);
            if (!this.alive || version !== this.navigationVersion || !LearningHttp.isCurrent(owner)) {
                return;
            }
            if (!resolved.success || resolved.book === null || resolved.chapters.length === 0) {
                throw new Error(resolved.message || '教材目录暂时不可用');
            }
            const valid: boolean = resolved.chapters.some((chapter: LearningChapterSummary): boolean => chapter.index === target.chapter_index);
            if (!valid) {
                throw new Error('这条记录对应的章节已变更，请从教材目录重新选择');
            }
            const frame: AgentFrame = new AgentFrame();
            frame.level = AgentLevel.READER;
            frame.target = target;
            frame.flowId = flowId;
            frame.book = resolved.book;
            frame.chapters = resolved.chapters;
            this.expectedFlowId = flowId;
            this.readerOverlayOpen = false;
            this.push(frame);
        } catch (error) {
            if (this.alive && version === this.navigationVersion) {
                this.errorText = agentFailure(error);
            }
        } finally {
            if (this.alive && version === this.navigationVersion) {
                this.opening = false;
            }
        }
    }

    private openReview(target: LearnTarget, flowId: string = ''): void {
        this.navigationVersion++;
        const frame: AgentFrame = new AgentFrame();
        frame.level = AgentLevel.REVIEW;
        frame.target = target;
        frame.flowId = flowId;
        this.push(frame);
    }

    private async openReport(target: LearnTarget): Promise<void> {
        const version: number = ++this.navigationVersion;
        try {
            const resolved: LearnTarget = await this.defaultTarget(target);
            if (!this.alive || version !== this.navigationVersion) {
                return;
            }
            const frame: AgentFrame = new AgentFrame();
            frame.level = AgentLevel.REPORT;
            frame.target = resolved;
            this.push(frame);
        } catch (error) {
            if (this.alive && version === this.navigationVersion) {
                this.errorText = agentFailure(error);
            }
        }
    }

    private openInspect(entry: TimelineEntry | null): void {
        this.navigationVersion++;
        const frame: AgentFrame = new AgentFrame();
        frame.level = AgentLevel.INSPECT;
        frame.entry = entry;
        frame.target = this.focus;
        this.push(frame);
    }

    private async openFlow(flowId: string): Promise<void> {
        const version: number = ++this.navigationVersion;
        try {
            const flow: FlowStateData = await LearningAgentApi.getFlow(flowId);
            if (!this.alive || version !== this.navigationVersion) {
                return;
            }
            if (flow.status === 'not_found') {
                throw new Error('这次学习流程已不存在');
            }
            if (flow.step !== 'opened') {
                this.openReview(flow.target, flowId);
            } else {
                await this.openReader(flow.target, flowId);
            }
        } catch (error) {
            if (this.alive && version === this.navigationVersion) {
                this.errorText = agentFailure(error);
            }
        }
    }

    private async respond(entry: TimelineEntry, response: string): Promise<void> {
        if (this.actionBusy.length > 0) {
            return;
        }
        this.actionBusy = entry.id;
        let decisionId: string = entry.id;
        for (const action of entry.actions || []) {
            if (action.action === 'decision_accept' && action.payload !== undefined) {
                decisionId = action.payload['decision_id'] || entry.id;
            }
        }
        try {
            const env: AgentEnvelope = await LearningAgentApi.respondDecision(decisionId, response);
            if (!this.alive) {
                return;
            }
            void this.refresh();
            if (response === 'accept') {
                let flowId: string = '';
                for (const action of env.next_actions || []) {
                    if (action.type === 'flow') {
                        flowId = action.flow_id || '';
                    }
                }
                if (flowId.length > 0) {
                    await this.openFlow(flowId);
                } else {
                    await this.openSession();
                }
            }
        } catch (error) {
            if (this.alive) {
                this.errorText = '选择尚未送到：' + agentFailure(error);
            }
        } finally {
            this.actionBusy = '';
        }
    }

    private openCard(entry: TimelineEntry): void {
        const card = entry.card;
        if (card === null || card === undefined) {
            return;
        }
        if (card.type === 'plan') {
            const target: LearnTarget | null | undefined = (card as PlanCard).target;
            if (target !== undefined && target !== null && target.book_id.length > 0) {
                void this.openReader(target);
            } else if (this.focus.book_id.length > 0) {
                this.errorText = '这张旧计划没有保存章节，将打开当前学习目标。';
                void this.openReader(this.focus);
            } else {
                void this.openSession();
            }
        } else if (card.type === 'prereq') {
            const prereq: PrereqCard = card as PrereqCard;
            const target: LearnTarget = { lecture_id: prereq.fromLectureId || '', lecture_title: prereq.fromCourse,
                book_id: prereq.fromBookId || '', book_title: '', chapter_index: prereq.fromChapterIndex !== undefined ? prereq.fromChapterIndex : -1,
                chapter_name: '', chapter_range: '' };
            if (target.lecture_id.length === 0 || target.book_id.length === 0 || target.chapter_index < 0) {
                this.errorText = '这张先修卡没有可用的章节定位';
                return;
            }
            void this.openReader(target);
        } else if (card.type === 'quiz') {
            const flowId: string = (card as QuizCard).flowId || '';
            if (flowId.length > 0) {
                this.openReview(this.focus, flowId);
            } else {
                this.errorText = '这张旧题卡没有复习流程，请从今日复习重新开始';
            }
        } else if (card.type === 'prep') {
            void this.openSession();
        }
    }

    private cardText(entry: TimelineEntry): string {
        const card = entry.card;
        if (card === null || card === undefined) { return ''; }
        if (card.type === 'proactive') { return (card as ProactiveCard).title; }
        if (card.type === 'plan') { return (card as PlanCard).chapter + '\n' + (card as PlanCard).why; }
        if (card.type === 'prep') { return (card as PrepCard).chapter + '\n' + ((card as PrepCard).highlights || []).join('\n'); }
        if (card.type === 'prereq') { return '先修：' + (card as PrereqCard).concept; }
        if (card.type === 'quiz') { return (card as QuizCard).stem; }
        if (card.type === 'wrapup') { return (card as WrapupCard).chapter + ' · 小测 ' + (card as WrapupCard).quizScore; }
        if (card.type === 'citation') { return (card as CitationCard).book + '\n' + (card as CitationCard).excerpt; }
        return '';
    }

    private timeLabel(entry: TimelineEntry): string {
        const date: Date = new Date(entry.ts);
        return (date.getMonth() + 1) + '/' + date.getDate() + ' ' + date.getHours() + ':' + (date.getMinutes() < 10 ? '0' : '') + date.getMinutes();
    }

    private async send(): Promise<void> {
        const text: string = this.draft.trim();
        if (text.length === 0 || this.sending) { return; }
        this.sending = true;
        this.errorText = '';
        try {
            if (/安排|计划|学什么|下一章|开始学习/.test(text)) {
                await LearningAgentApi.plan(text);
            } else {
                await LearningAgentApi.ask(text, this.focus.book_id.length > 0 ? this.focus : null);
            }
            if (this.alive) {
                this.draft = '';
                await this.refresh();
            }
        } catch (error) {
            if (this.alive) { this.errorText = agentFailure(error); }
        } finally {
            this.sending = false;
        }
    }

    @Builder
    EntryCard(entry: TimelineEntry) {
        Column({ space: 10 }) {
            Text((entry.kind === 'user_msg' ? '我' : '学习助手') + ' · ' + this.timeLabel(entry))
                .fontSize(12).fontColor($r('app.color.text_secondary')).width('100%')
            MarkdownView({ source: entry.text }).width('100%')
            if (this.cardText(entry).length > 0) {
                Text(this.cardText(entry)).fontColor($r('app.color.text_primary')).width('100%')
            }
            if (entry.card !== undefined && entry.card !== null) {
                if (entry.card.type === 'proactive') {
                    if (entry.status === undefined || entry.status === 'pending') {
                        Row({ space: 8 }) {
                            Button('好').layoutWeight(1).enabled(this.actionBusy.length === 0).onClick(() => { void this.respond(entry, 'accept'); })
                            Button('晚点').layoutWeight(1).enabled(this.actionBusy.length === 0).onClick(() => { void this.respond(entry, 'defer'); })
                            Button('不用了').layoutWeight(1).enabled(this.actionBusy.length === 0).onClick(() => { void this.respond(entry, 'dismiss'); })
                        }.width('100%')
                    } else {
                        Text(entry.status === 'accept' ? '已接受' : entry.status === 'defer' ? '稍后再安排' : '这条安排已结束')
                            .fontColor($r('app.color.text_secondary')).width('100%')
                    }
                } else if (entry.card.type === 'plan' || entry.card.type === 'prep' || entry.card.type === 'prereq' || entry.card.type === 'quiz') {
                    Button(entry.card.type === 'quiz' ? '开始答题' : '开始阅读').width('100%').enabled(!this.opening)
                        .onClick(() => { this.openCard(entry); })
                }
            }
            Button('查看依据').fontSize(12).onClick(() => { this.openInspect(entry); })
        }.width('100%').padding(16).borderRadius(16).backgroundColor($r('app.color.bg_card'))
            .border({ width: entry.id === this.launchDecision ? 1 : 0, color: $r('app.color.brand_primary') })
            .gesture(LongPressGesture().onAction(() => { this.openInspect(entry); }))
    }

    @Builder
    Day() {
        Column({ space: 12 }) {
            Row() {
                Button('返回').onClick(() => { this.onBack(); })
                Text('学习助手').fontSize(20).fontColor($r('app.color.text_primary')).fontWeight(FontWeight.Medium).layoutWeight(1).textAlign(TextAlign.Center)
                Button('去学习').onClick(() => { this.onOpenLearning(); })
            }.width('100%').padding({ left: 16, right: 16, top: 12 })
            Text(this.todayText).fontColor($r('app.color.text_secondary')).width('100%').padding({ left: 16, right: 16 })
            Row({ space: 8 }) {
                Button('继续读').layoutWeight(1).enabled(!this.opening).onClick(() => { void this.openSession(); })
                Button('复习').layoutWeight(1).onClick(() => { this.openReview(this.focus); })
                Button('认知').layoutWeight(1).onClick(() => { this.openInspect(null); })
                Button('刷新').layoutWeight(1).onClick(() => { void this.refresh(); })
            }.width('100%').padding({ left: 16, right: 16 })
            if (this.errorText.length > 0) {
                Text(this.errorText).fontColor($r('app.color.text_danger')).width('100%').padding({ left: 16, right: 16 })
            }
            if (this.loading && this.entries.length === 0 || this.opening) {
                LoadingProgress().width(28).height(28)
            }
            List({ scroller: this.scroller, space: 12 }) {
                ForEach(this.entries, (entry: TimelineEntry) => {
                    ListItem() { this.EntryCard(entry) }
                }, (entry: TimelineEntry) => entry.id + ':' + (entry.status || '') + ':' + entry.ts)
                if (!this.loading && this.entries.length === 0) {
                    ListItem() { Text('开始阅读后，学习与复习记录会显示在这里。').fontColor($r('app.color.text_secondary')).padding(16) }
                }
            }.width('100%').layoutWeight(1).padding({ left: 16, right: 16 }).scrollBar(BarState.Auto)
            Row({ space: 8 }) {
                TextInput({ text: this.draft, placeholder: '问一个问题，或安排今天的学习' }).layoutWeight(1).onChange((value: string) => { this.draft = value; })
                Button(this.sending ? '发送中' : '发送').enabled(!this.sending && this.draft.trim().length > 0).onClick(() => { void this.send(); })
            }.width('100%').padding({ left: 16, right: 16, bottom: 20 })
        }.width('100%').height('100%').backgroundColor($r('app.color.bg_page'))
    }

    @Builder
    Frame(frame: AgentFrame, index: number) {
        if (frame.level === AgentLevel.DAY) {
            this.Day()
        } else if (frame.level === AgentLevel.READER) {
            LearningReader({
                app: this.app, lectureId: frame.target.lecture_id, book: frame.book, chapters: frame.chapters,
                startChapterIndex: frame.target.chapter_index, initialParagraph: -1,
                flowId: frame.flowId, flowChapterIndex: frame.target.chapter_index,
                visible: this.active(frame), navDepth: $navDepth, navLevel: index,
                readerOverlayOpen: $readerOverlayOpen, readerBackToken: $readerBackToken,
                onBack: () => { this.goBack(); }, onOpenImage: (url: string) => { this.onOpenImage(url); }
            }).width('100%').height('100%')
        } else if (frame.level === AgentLevel.REVIEW) {
            LearningAgentReview({ initialTarget: frame.target, flowId: frame.flowId, visible: this.active(frame),
                onBack: () => { this.goBack(); },
                onRead: (target: LearnTarget, flowId: string) => { void this.openReader(target, flowId); },
                onSubmitted: () => { void this.refresh(); }
            }).width('100%').height('100%')
        } else if (frame.level === AgentLevel.REPORT) {
            LearningAgentReport({ target: frame.target, visible: this.active(frame), onBack: () => { this.goBack(); },
                onRead: (target: LearnTarget) => { void this.openReader(target); },
                onReview: (target: LearnTarget) => { this.openReview(target); }
            }).width('100%').height('100%')
        } else if (frame.level === AgentLevel.INSPECT) {
            Column() {
                Blank().height('12%').onClick(() => { this.goBack(); })
                LearningAgentInspect({ entry: frame.entry, fallbackTarget: frame.target,
                    onClose: () => { this.goBack(); }, onChanged: () => { void this.refresh(); },
                    onReport: (target: LearnTarget) => { this.goBack(); void this.openReport(target); }
                }).width('100%').layoutWeight(1).borderRadius({ topLeft: 24, topRight: 24 }).clip(true)
            }.width('100%').height('100%').backgroundColor('#66000000')
        }
    }

    build() {
        Stack() {
            ForEach(this.frames, (frame: AgentFrame, index: number) => {
                Stack() { this.Frame(frame, index) }
                    .width('100%').height('100%')
                    .visibility(this.top().id === frame.id || this.top().level === AgentLevel.INSPECT && index === this.frames.length - 2 ? Visibility.Visible : Visibility.Hidden)
                    .hitTestBehavior(this.top().id === frame.id ? HitTestMode.Default : HitTestMode.None)
            }, (frame: AgentFrame) => String(frame.id))
        }.width('100%').height('100%').backgroundColor($r('app.color.bg_page'))
    }
}

import { LearningAgentApi, agentFailure, NO_AGENT_TARGET } from '../../common/LearningAgentApi';
import { LearnTarget, ReportPayload, ReportSummary, ReportNote, GraphChapter, GraphConcept, GraphRelation } from '../../common/LearningAgentModels';

// Cognition / knowledge graph report, kept separate from course statistics in LearningReportView.
@Component
export struct LearningAgentReport {
    @Prop target: LearnTarget = NO_AGENT_TARGET;
    @Prop @Watch('onVisibleChanged') visible: boolean = true;
    @StorageProp('nxLearningBridgeTick') @Watch('onBridgeChanged') private bridgeTick: number = 0;
    onBack: () => void = () => {};
    onRead: (target: LearnTarget) => void = () => {};
    onReview: (target: LearnTarget) => void = () => {};
    @State private loading: boolean = true;
    @State private errorText: string = '';
    @State private graphError: string = '';
    @State private summary: ReportSummary | null = null;
    @State private weaknesses: ReportNote[] = [];
    @State private recommendations: ReportNote[] = [];
    @State private chapters: GraphChapter[] = [];
    @State private relations: GraphRelation[] = [];
    private version: number = 0;
    private alive: boolean = false;

    aboutToAppear(): void {
        this.alive = true;
        void this.load();
    }

    aboutToDisappear(): void {
        this.alive = false;
        this.version++;
    }

    private onVisibleChanged(): void {
        if (this.visible && this.alive) {
            void this.load();
        }
    }

    private onBridgeChanged(): void {
        if (this.visible && this.alive) {
            void this.load();
        }
    }

    private async load(): Promise<void> {
        const version: number = ++this.version;
        this.loading = true;
        this.errorText = '';
        void this.loadGraph(version);
        try {
            const data: ReportPayload = await LearningAgentApi.getReport(this.target);
            if (!this.alive || version !== this.version) {
                return;
            }
            this.summary = data.summary;
            this.weaknesses = data.weaknesses || [];
            this.recommendations = data.recommendations || [];
        } catch (error) {
            if (this.alive && version === this.version) {
                this.errorText = agentFailure(error);
            }
        } finally {
            if (this.alive && version === this.version) {
                this.loading = false;
            }
        }
    }

    private async loadGraph(version: number): Promise<void> {
        this.graphError = '';
        try {
            const data = await LearningAgentApi.getGraph(this.target);
            if (!this.alive || version !== this.version) {
                return;
            }
            this.chapters = data.graph !== null ? data.graph.chapters || [] : [];
            this.relations = data.graph !== null ? data.graph.relations || [] : [];
        } catch (error) {
            if (this.alive && version === this.version) {
                this.graphError = '概念关系暂时没同步上：' + agentFailure(error);
            }
        }
    }

    private chapterTarget(chapter: GraphChapter, index: number): LearnTarget {
        return { lecture_id: this.target.lecture_id, lecture_title: this.target.lecture_title,
            book_id: this.target.book_id, book_title: this.target.book_title,
            chapter_index: chapter.chapter_index !== undefined ? chapter.chapter_index : index,
            chapter_name: chapter.name, chapter_range: '' };
    }

    private readingLabel(): string {
        if (this.summary === null) {
            return '';
        }
        const percent: number = this.summary.reading_progress_percent !== undefined
            ? this.summary.reading_progress_percent : this.summary.progress_percent;
        return '阅读覆盖 ' + Math.round(percent * 10) / 10 + '% · 已读完 ' + this.summary.completed_chapters + '/' + this.summary.total_chapters + ' 章';
    }

    private accuracyLabel(): string {
        if (this.summary === null || this.summary.accuracy === null || this.summary.accuracy === undefined) {
            return '还没有足够的作答记录';
        }
        return '已答 ' + this.summary.submitted_questions + ' 题 · 正确率 ' + Math.round(this.summary.accuracy * 100) + '%';
    }

    private masteryLabel(concept: GraphConcept): string {
        return concept.mastery !== undefined && concept.mastery !== null
            ? ' · 掌握度 ' + Math.round(concept.mastery * 100) + '%' : ' · 待验证';
    }

    build() {
        Column({ space: 12 }) {
            Row() {
                Button('返回').onClick(() => { this.onBack(); })
                Text('学习报告与图谱').fontSize(20).fontWeight(FontWeight.Medium).fontColor($r('app.color.text_primary')).layoutWeight(1).textAlign(TextAlign.Center)
                Button('刷新').onClick(() => { void this.load(); })
            }.width('100%').padding({ left: 16, right: 16, top: 12 })
            Scroll() {
                Column({ space: 16 }) {
                    Text(this.target.book_title || this.target.lecture_title).fontSize(20).fontColor($r('app.color.text_primary')).width('100%')
                    if (this.loading) {
                        LoadingProgress().width(32).height(32)
                    }
                    if (this.errorText.length > 0) {
                        Text(this.errorText).fontColor($r('app.color.text_danger')).width('100%')
                    }
                    if (this.summary !== null) {
                        Text(this.readingLabel()).fontColor($r('app.color.text_primary')).width('100%')
                        Text(this.accuracyLabel()).fontColor($r('app.color.text_secondary')).width('100%')
                    }
                    ForEach(this.weaknesses, (note: ReportNote) => {
                        Column({ space: 8 }) {
                            Text(note.title).fontWeight(FontWeight.Medium).fontColor($r('app.color.text_primary')).width('100%')
                            Text(note.detail).fontColor($r('app.color.text_secondary')).width('100%')
                        }.padding(16).borderRadius(16).backgroundColor($r('app.color.bg_card')).width('100%')
                    }, (note: ReportNote, index: number) => note.title + ':' + note.detail + ':' + index)
                    ForEach(this.recommendations, (note: ReportNote) => {
                        Text(note.title + '：' + note.detail).fontColor($r('app.color.text_secondary')).width('100%')
                    }, (note: ReportNote, index: number) => note.title + ':' + note.detail + ':' + index)
                    Row({ space: 12 }) {
                        Button('继续阅读').layoutWeight(1).onClick(() => { this.onRead(this.target); })
                        Button('复习这一章').layoutWeight(1).onClick(() => { this.onReview(this.target); })
                    }.width('100%')
                    Text('章节与概念').fontSize(18).fontWeight(FontWeight.Medium).fontColor($r('app.color.text_primary')).width('100%')
                    if (this.graphError.length > 0) {
                        Text(this.graphError).fontColor($r('app.color.text_danger')).width('100%')
                    } else if (this.chapters.length === 0 && !this.loading) {
                        Text('这本教材的概念图谱还未生成。').fontColor($r('app.color.text_secondary')).width('100%')
                    }
                    ForEach(this.chapters, (chapter: GraphChapter, index: number) => {
                        Column({ space: 10 }) {
                            Text(chapter.name).fontSize(17).fontWeight(FontWeight.Medium).fontColor($r('app.color.text_primary')).width('100%')
                            Text(chapter.summary).fontColor($r('app.color.text_secondary')).width('100%')
                            ForEach(chapter.concepts || [], (concept: GraphConcept) => {
                                Text(concept.name + this.masteryLabel(concept) + (concept.detail ? '\n' + concept.detail : ''))
                                    .fontColor($r('app.color.text_secondary')).width('100%')
                            }, (concept: GraphConcept, conceptIndex: number) => concept.name + ':' + concept.mastery + ':' + conceptIndex)
                            Row({ space: 12 }) {
                                Button('读这一章').layoutWeight(1).onClick(() => { this.onRead(this.chapterTarget(chapter, index)); })
                                Button('练这一章').layoutWeight(1).onClick(() => { this.onReview(this.chapterTarget(chapter, index)); })
                            }.width('100%')
                        }.padding(16).borderRadius(16).backgroundColor($r('app.color.bg_card')).width('100%')
                    }, (chapter: GraphChapter, index: number) => chapter.name + ':' + index)
                    ForEach(this.relations, (relation: GraphRelation) => {
                        Text(relation.from + ' → ' + relation.to + (relation.label ? ' · ' + relation.label : ''))
                            .fontSize(13).fontColor($r('app.color.text_secondary')).width('100%')
                    }, (relation: GraphRelation, index: number) => relation.from + ':' + relation.to + ':' + index)
                }.width('100%').padding({ left: 16, right: 16, bottom: 32 })
            }.layoutWeight(1).width('100%')
        }.width('100%').height('100%').backgroundColor($r('app.color.bg_page'))
    }
}

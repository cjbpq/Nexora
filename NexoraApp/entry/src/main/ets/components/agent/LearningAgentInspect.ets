import { LearningAgentApi, agentFailure, NO_AGENT_TARGET } from '../../common/LearningAgentApi';
import { LearnTarget, TimelineEntry, MirrorFacet, MirrorMasteryCell, MirrorCourse, MirrorEvidenceRef } from '../../common/LearningAgentModels';

@Component
export struct LearningAgentInspect {
    @Prop entry: TimelineEntry | null = null;
    @Prop fallbackTarget: LearnTarget = NO_AGENT_TARGET;
    onClose: () => void = () => {};
    onReport: (target: LearnTarget) => void = () => {};
    onChanged: () => void = () => {};
    @State private loading: boolean = true;
    @State private errorText: string = '';
    @State private facets: MirrorFacet[] = [];
    @State private mastery: MirrorMasteryCell[] = [];
    @State private courses: MirrorCourse[] = [];
    @State private busy: string = '';
    private alive: boolean = false;
    private version: number = 0;

    aboutToAppear(): void {
        this.alive = true;
        void this.load();
    }

    aboutToDisappear(): void {
        this.alive = false;
        this.version++;
    }

    private async load(): Promise<void> {
        const version: number = ++this.version;
        this.loading = true;
        this.errorText = '';
        try {
            const overview = await LearningAgentApi.cognition();
            if (!this.alive || version !== this.version) {
                return;
            }
            this.facets = overview.facets || [];
            this.mastery = overview.mastery || [];
            this.courses = overview.courses || [];
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

    private async respond(facet: MirrorFacet, value: string): Promise<void> {
        if (this.busy.length > 0) {
            return;
        }
        this.busy = facet.id;
        try {
            await LearningAgentApi.verdict(facet, value);
            if (this.alive) {
                this.onChanged();
                await this.load();
            }
        } catch (error) {
            if (this.alive) {
                this.errorText = agentFailure(error);
            }
        } finally {
            this.busy = '';
        }
    }

    private reportTarget(): LearnTarget {
        if (this.fallbackTarget.book_id.length > 0) {
            return this.fallbackTarget;
        }
        if (this.courses.length > 0) {
            const course: MirrorCourse = this.courses[0];
            return { lecture_id: course.lecture_id, lecture_title: course.title, book_id: course.book_id || '',
                book_title: '', chapter_index: 0, chapter_name: '', chapter_range: '' };
        }
        if (this.facets.length > 0) {
            const facet: MirrorFacet = this.facets[0];
            return { lecture_id: facet.lectureId, lecture_title: '', book_id: facet.bookId, book_title: '',
                chapter_index: 0, chapter_name: '', chapter_range: '' };
        }
        return NO_AGENT_TARGET;
    }

    private evidenceLabel(evidence: MirrorEvidenceRef): string {
        const source: string = evidence.source === 'reading' || evidence.source === 'progress' ? '阅读记录'
            : evidence.source === 'quiz' || evidence.source === 'review' ? '作答记录'
            : evidence.source === 'memory' || evidence.source === 'conversation' || evidence.source === 'app' ? '你的原话' : '推断依据';
        return source + ' · ' + evidence.label;
    }

    private contextText(): string {
        if (this.entry === null || this.entry.context === undefined || this.entry.context === null) {
            return '';
        }
        const context = this.entry.context;
        const lines: string[] = [];
        if (context.time) { lines.push(context.time + ' ' + (context.weekday || '')); }
        if (context.scene) { lines.push('场景：' + context.scene); }
        if (context.location) { lines.push('位置：' + context.location); }
        if (context.dnd) { lines.push('当时开启免打扰'); }
        if ((context.calendar || []).length > 0) { lines.push('日程：' + context.calendar.join('；')); }
        if ((context.at_risk || []).length > 0) { lines.push('待复习：' + context.at_risk.join('、')); }
        if ((context.confusion || []).length > 0) { lines.push('疑问：' + context.confusion.join('、')); }
        return lines.join('\n');
    }

    build() {
        Column({ space: 12 }) {
            Row() {
                Text('决策与认知').fontSize(20).fontWeight(FontWeight.Medium).fontColor($r('app.color.text_primary')).layoutWeight(1)
                Button('关闭').onClick(() => { this.onClose(); })
            }.width('100%').padding(16)
            Scroll() {
                Column({ space: 16 }) {
                    if (this.entry !== null) {
                        Text(this.entry.text).fontSize(17).fontColor($r('app.color.text_primary')).width('100%')
                        Text(this.entry.reason || '这条记录没有额外的决策说明。').fontColor($r('app.color.text_secondary')).width('100%')
                        if (this.entry.judgment !== undefined && this.entry.judgment !== null) {
                            Text((this.entry.judgment.source === 'model' ? '模型判断' : '规则判断') + ' · 把握 ' + Math.round(this.entry.judgment.confidence * 100) + '%')
                                .fontColor($r('app.color.text_secondary')).width('100%')
                        }
                        if (this.contextText().length > 0) {
                            Text(this.contextText()).fontColor($r('app.color.text_secondary')).width('100%')
                        }
                    }
                    if (this.loading) {
                        LoadingProgress().width(32).height(32)
                    }
                    if (this.errorText.length > 0) {
                        Text(this.errorText).fontColor($r('app.color.text_danger')).width('100%')
                        Button('重新同步').onClick(() => { void this.load(); })
                    }
                    Text('对你的理解').fontSize(18).fontColor($r('app.color.text_primary')).width('100%')
                    if (!this.loading && this.facets.length === 0) {
                        Text('阅读和复习后，新的认知记录会显示在这里。').fontColor($r('app.color.text_secondary')).width('100%')
                    }
                    ForEach(this.facets, (facet: MirrorFacet) => {
                        Column({ space: 10 }) {
                            Text(facet.claim).fontColor($r('app.color.text_primary')).width('100%')
                            ForEach(facet.evidence || [], (evidence: MirrorEvidenceRef) => {
                                Text(this.evidenceLabel(evidence)).fontSize(13).fontColor($r('app.color.text_secondary')).width('100%')
                            }, (evidence: MirrorEvidenceRef, index: number) => evidence.source + ':' + evidence.label + ':' + index)
                            Row({ space: 12 }) {
                                Button(facet.userVerdict === 'agree' ? '已认可' : '符合我的情况').layoutWeight(1).enabled(this.busy.length === 0)
                                    .onClick(() => { void this.respond(facet, 'agree'); })
                                Button(facet.userVerdict === 'disagree' ? '已纠正' : '不太符合').layoutWeight(1).enabled(this.busy.length === 0)
                                    .onClick(() => { void this.respond(facet, 'disagree'); })
                            }.width('100%')
                        }.padding(16).borderRadius(16).backgroundColor($r('app.color.bg_card')).width('100%')
                    }, (facet: MirrorFacet) => facet.id + ':' + facet.userVerdict)
                    ForEach(this.mastery, (cell: MirrorMasteryCell) => {
                        Text(cell.concept + (cell.mastery !== null ? ' · 掌握度 ' + Math.round(cell.mastery * 100) + '%' : ' · 待验证'))
                            .fontColor($r('app.color.text_secondary')).width('100%')
                    }, (cell: MirrorMasteryCell, index: number) => cell.concept + ':' + cell.mastery + ':' + index)
                    Button('查看学习报告与图谱').width('100%').onClick(() => { this.onReport(this.reportTarget()); })
                }.padding({ left: 16, right: 16, bottom: 32 }).width('100%')
            }.layoutWeight(1).width('100%')
        }.width('100%').height('100%').backgroundColor($r('app.color.bg_page'))
    }
}

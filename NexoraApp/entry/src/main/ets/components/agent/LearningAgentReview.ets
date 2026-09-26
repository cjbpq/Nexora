import { LearningApi, LearningChapterSummary } from '../../common/LearningApi';
import { LearningAgentApi, agentFailure, NO_AGENT_TARGET } from '../../common/LearningAgentApi';
import { LearningBridge } from '../../common/LearningBridge';
import {
    LearnTarget, ContextData, TaskInfo, TaskData, ReviewQuestion, ReviewAnswerDraft,
    ReviewSubmitData, ReviewSubmitItem, FlowStateData, FlowSubmitData
} from '../../common/LearningAgentModels';
import { MarkdownView } from '../chat/MarkdownBlock';

// TodayTask and flow Quiz share rendering, while keeping their submission identities separate.
@Component
export struct LearningAgentReview {
    @Prop initialTarget: LearnTarget = NO_AGENT_TARGET;
    @Prop flowId: string = '';
    @Prop @Watch('onVisibleChanged') visible: boolean = true;
    @StorageProp('nxLearningBridgeTick') @Watch('onBridgeChanged') private bridgeTick: number = 0;
    onBack: () => void = () => {};
    onRead: (target: LearnTarget, flowId: string) => void = () => {};
    onSubmitted: () => void = () => {};
    @State private choices: LearnTarget[] = [];
    @State private selected: LearnTarget = NO_AGENT_TARGET;
    @State private chapters: LearningChapterSummary[] = [];
    @State private questions: ReviewQuestion[] = [];
    @State private answers: string[] = [];
    @State private origin: LearnTarget = NO_AGENT_TARGET;
    @State private loading: boolean = true;
    @State private generating: boolean = false;
    @State private submitting: boolean = false;
    @State private submitted: boolean = false;
    @State private errorText: string = '';
    @State private statusText: string = '';
    @State private resultText: string = '';
    @State private needsReading: boolean = false;
    private taskId: string = '';
    private quizId: string = '';
    private attemptId: string = '';
    private version: number = 0;
    private choiceVersion: number = 0;
    private contextVersion: number = 0;
    private timer: number = -1;
    private alive: boolean = false;
    private polling: boolean = false;
    private flowRefreshPending: boolean = false;

    aboutToAppear(): void {
        this.alive = true;
        if (this.flowId.length > 0) {
            void this.loadFlow();
        } else {
            void this.loadChoices();
        }
    }

    aboutToDisappear(): void {
        this.alive = false;
        this.version++;
        this.choiceVersion++;
        this.contextVersion++;
        this.stopTimer();
    }

    private onVisibleChanged(): void {
        if (!this.visible) {
            this.stopTimer();
            return;
        }
        if (this.flowId.length > 0 && !this.submitted) {
            void this.loadFlow();
        } else if (this.generating && this.taskId.length > 0) {
            void this.pollTask(this.version);
        }
    }

    private onBridgeChanged(): void {
        const event = LearningBridge.latest();
        if (this.alive && event !== null && event.type === 'flow_reading_done' && event.flowId === this.flowId) {
            this.flowRefreshPending = true;
            if (this.visible) {
                void this.loadFlow();
            }
        }
    }

    private stopTimer(): void {
        if (this.timer >= 0) {
            clearTimeout(this.timer);
            this.timer = -1;
        }
    }

    private async loadChoices(): Promise<void> {
        const version: number = ++this.contextVersion;
        this.loading = true;
        this.errorText = '';
        try {
            const context: ContextData = await LearningAgentApi.getContext();
            if (!this.alive || version !== this.contextVersion) {
                return;
            }
            const choices: LearnTarget[] = [];
            for (const lecture of context.lectures) {
                for (const book of lecture.books) {
                    let chapterIndex: number = lecture.current_book_id === book.id &&
                        lecture.current_chapter_index !== undefined && lecture.current_chapter_index !== null
                        ? Math.max(0, lecture.current_chapter_index) : 0;
                    if (context.active_session !== undefined && context.active_session.lecture_id === lecture.id &&
                        context.active_session.book_id === book.id) {
                        chapterIndex = Math.max(0, context.active_session.chapter_index);
                    }
                    choices.push({ lecture_id: lecture.id, lecture_title: lecture.title,
                        book_id: book.id, book_title: book.title, chapter_index: chapterIndex,
                        chapter_name: '', chapter_range: '' });
                }
            }
            this.choices = choices;
            let selected: LearnTarget | null = null;
            const requestedTarget: LearnTarget = this.initialTarget;
            for (const choice of choices) {
                if (choice.lecture_id === requestedTarget.lecture_id && choice.book_id === requestedTarget.book_id) {
                    selected = requestedTarget;
                }
            }
            if (selected === null && choices.length > 0) {
                selected = choices[0];
            }
            if (selected === null) {
                this.statusText = '先去学习选择教材，再来复习。';
            } else {
                await this.chooseBook(selected);
            }
            if (!this.alive || version !== this.contextVersion) {
                return;
            }
            const pending: string = AppStorage.get<string>('nxPendingReviewTask') || '';
            if (pending.length > 0 && this.alive) {
                AppStorage.setOrCreate('nxPendingReviewTask', '');
                this.taskId = pending;
                this.generating = true;
                void this.pollTask(++this.version);
            }
        } catch (error) {
            if (this.alive && version === this.contextVersion) {
                this.errorText = agentFailure(error);
            }
        } finally {
            if (this.alive && version === this.contextVersion) {
                this.loading = false;
            }
        }
    }

    private async chooseBook(target: LearnTarget): Promise<void> {
        this.selected = target;
        this.chapters = [];
        const version: number = ++this.choiceVersion;
        const result = await LearningApi.shared.getBookChapters(target.lecture_id, target.book_id);
        if (!this.alive || version !== this.choiceVersion) {
            return;
        }
        if (!result.success) {
            this.errorText = result.message;
            return;
        }
        this.chapters = result.chapters;
        let chapter: LearningChapterSummary | null = null;
        for (const item of this.chapters) {
            if (item.index === target.chapter_index) {
                chapter = item;
            }
        }
        if (chapter === null && this.chapters.length > 0) {
            chapter = this.chapters[0];
        }
        if (chapter !== null) {
            this.chooseChapter(chapter);
        }
    }

    private chooseChapter(chapter: LearningChapterSummary): void {
        this.selected = {
            lecture_id: this.selected.lecture_id, lecture_title: this.selected.lecture_title,
            book_id: this.selected.book_id, book_title: this.selected.book_title,
            chapter_index: chapter.index, chapter_name: chapter.title, chapter_range: ''
        };
    }

    private async startReview(): Promise<void> {
        if (this.generating || this.submitting || this.selected.book_id.length === 0) {
            return;
        }
        this.stopTimer();
        const version: number = ++this.version;
        this.origin = this.selected;
        this.questions = [];
        this.answers = [];
        this.resultText = '';
        this.errorText = '';
        this.submitted = false;
        this.generating = true;
        this.taskId = '';
        this.quizId = '';
        this.attemptId = '';
        this.statusText = '正在按这一章准备复习题…';
        try {
            const data: TaskData = await LearningAgentApi.reviewPlan(this.origin);
            if (!this.alive || version !== this.version) {
                return;
            }
            this.taskId = data.task.task_id;
            if (!this.consumeTask(data.task)) {
                void this.pollTask(version);
            }
        } catch (error) {
            if (this.alive && version === this.version) {
                this.errorText = agentFailure(error);
                this.generating = false;
            }
        }
    }

    private consumeTask(task: TaskInfo): boolean {
        if (task.status === 'failed') {
            this.generating = false;
            this.errorText = task.error !== null && task.error !== undefined ? task.error.message : '出题失败，请重新生成';
            return true;
        }
        if (task.status !== 'completed') {
            return false;
        }
        this.generating = false;
        this.quizId = task.result.quiz_id;
        this.attemptId = task.result.attempt_id || task.task_id;
        this.origin = { lecture_id: task.result.lecture_id, lecture_title: this.origin.lecture_title,
            book_id: task.result.book_id, book_title: this.origin.book_title,
            chapter_index: task.result.chapter_index, chapter_name: task.result.chapter_name, chapter_range: '' };
        this.replaceQuestions(task.result.questions || []);
        this.statusText = this.questions.length > 0 ? '准备好了。提交后会更新你的学习记录。' : '本次没有生成题目，可以再试一次。';
        return true;
    }

    private async pollTask(version: number): Promise<void> {
        if (!this.alive || !this.visible || this.polling || version !== this.version) {
            return;
        }
        this.polling = true;
        try {
            const data: TaskData = await LearningAgentApi.getTask(this.taskId);
            if (this.alive && version === this.version) {
                this.errorText = '';
                this.consumeTask(data.task);
            }
        } catch (error) {
            if (this.alive && version === this.version) {
                this.errorText = '暂时没同步上：' + agentFailure(error);
            }
        } finally {
            this.polling = false;
            if (this.alive && this.visible && this.generating && version === this.version) {
                this.timer = setTimeout(() => { void this.pollTask(version); }, 2000);
            }
        }
    }

    private async loadFlow(): Promise<void> {
        if (!this.alive || !this.visible || this.submitting) {
            return;
        }
        if (this.polling) {
            this.flowRefreshPending = true;
            return;
        }
        this.stopTimer();
        this.flowRefreshPending = false;
        const version: number = this.version;
        this.polling = true;
        try {
            const flow: FlowStateData = await LearningAgentApi.getFlow(this.flowId);
            if (!this.alive || version !== this.version) {
                return;
            }
            if (flow.status === 'not_found') {
                throw new Error('这次复习流程已不可用，请回时间线重新开始');
            }
            this.origin = flow.target;
            this.selected = flow.target;
            this.errorText = '';
            this.needsReading = flow.step === 'opened';
            if (flow.status === 'done') {
                this.submitted = true;
                this.generating = false;
                this.resultText = flow.wrapup !== undefined ? flow.wrapup.quizScore : '本次复习已完成';
            } else if (flow.quiz !== undefined && flow.quiz.status === 'completed') {
                const questions: ReviewQuestion[] = [];
                for (const question of flow.quiz.questions) {
                    questions.push({ type: question.type, title: question.title, content: question.content,
                        options: question.options || [], source_id: question.source_id, source: question.source,
                        answer: question.answer, difficulty: '', hint: '' });
                }
                this.replaceQuestions(questions);
                this.generating = false;
                this.statusText = '读完后的复习题已经准备好。';
            } else if (flow.quiz !== undefined && flow.quiz.status === 'failed') {
                this.generating = false;
                this.errorText = flow.quiz.error || '本次出题失败，请返回时间线查看';
            } else {
                this.generating = !this.needsReading;
                this.statusText = this.needsReading ? '先读完目标章节，再回来做题。' : '已收到阅读完成记录，正在准备题目…';
            }
        } catch (error) {
            if (this.alive && version === this.version) {
                this.errorText = agentFailure(error);
                this.generating = false;
            }
        } finally {
            this.polling = false;
            this.loading = false;
            if (this.alive && this.visible && (this.generating || this.flowRefreshPending) && version === this.version) {
                this.timer = setTimeout(() => { void this.loadFlow(); }, this.flowRefreshPending ? 0 : 2000);
            }
        }
    }

    private questionId(question: ReviewQuestion, index: number): string {
        return question.source_id !== undefined && question.source_id.length > 0 ? question.source_id : 'q' + index;
    }

    private replaceQuestions(next: ReviewQuestion[]): void {
        const previous: Map<string, string> = new Map<string, string>();
        for (let index: number = 0; index < this.questions.length; index++) {
            previous.set(this.questionId(this.questions[index], index), this.answers[index] || '');
        }
        this.questions = next;
        this.answers = next.map((question: ReviewQuestion, index: number): string =>
            previous.get(this.questionId(question, index)) || '');
    }

    private options(question: ReviewQuestion): string[] {
        if (question.type === 'text' || question.type === 'short_answer' || question.type === '简答题') {
            return [];
        }
        const result: string[] = (question.options || []).filter((option: string): boolean =>
            option.trim().length > 0 && ['无', '暂无', 'none', 'n/a', '-', '—', '选项', '略'].indexOf(option.trim().toLowerCase()) < 0);
        return result.length >= 2 ? result : [];
    }

    private setAnswer(index: number, answer: string): void {
        const next: string[] = this.answers.slice();
        next[index] = answer;
        this.answers = next;
    }

    private async submit(): Promise<void> {
        if (this.submitting || this.submitted || this.questions.length === 0) {
            return;
        }
        if (this.answers.some((answer: string): boolean => answer.trim().length === 0)) {
            this.errorText = '还有题目没回答，写下你的想法后再提交。';
            return;
        }
        this.submitting = true;
        this.errorText = '';
        const version: number = this.version;
        const answers: ReviewAnswerDraft[] = this.questions.map((question: ReviewQuestion, index: number): ReviewAnswerDraft => ({
            question_id: this.questionId(question, index), answer: this.answers[index].trim()
        }));
        try {
            let result: string = '';
            if (this.flowId.length > 0) {
                const response: FlowSubmitData = await LearningAgentApi.submitFlow(this.flowId, answers);
                result = response.state.wrapup !== undefined ? response.state.wrapup.quizScore : '已完成，验收卡已写入时间线';
            } else {
                const response: ReviewSubmitData = await LearningAgentApi.submitReview(this.quizId, this.attemptId, this.origin, answers);
                result = response.score;
                if (response.items.length > 0 && response.items.every((item: ReviewSubmitItem): boolean => item.duplicate === true)) {
                    result += '（本轮已记录的成绩）';
                }
            }
            if (this.alive && version === this.version) {
                this.resultText = result;
                this.submitted = true;
                this.onSubmitted();
            }
        } catch (error) {
            if (this.alive && version === this.version) {
                this.errorText = '提交失败，答案已保留：' + agentFailure(error);
            }
        } finally {
            if (this.alive) {
                this.submitting = false;
            }
        }
    }

    private bookOptions(): SelectOption[] {
        return this.choices.map((target: LearnTarget): SelectOption => ({ value: target.book_title }));
    }

    private chapterOptions(): SelectOption[] {
        return this.chapters.map((chapter: LearningChapterSummary): SelectOption => ({ value: chapter.title }));
    }

    build() {
        Column({ space: 12 }) {
            Row() {
                Button('返回').onClick(() => { this.onBack(); })
                Text(this.flowId.length > 0 ? '读后小测' : '今日复习').fontSize(20).fontWeight(FontWeight.Medium).layoutWeight(1).textAlign(TextAlign.Center)
                Button('回读').enabled(this.selected.book_id.length > 0).onClick(() => { this.onRead(this.selected, this.flowId); })
            }.width('100%').padding({ left: 16, right: 16, top: 12 })
            Scroll() {
                Column({ space: 16 }) {
                    if (this.loading) {
                        LoadingProgress().width(32).height(32)
                    }
                    if (this.flowId.length === 0 && this.choices.length > 0) {
                        Select(this.bookOptions()).value(this.selected.book_title).width('100%').enabled(!this.loading && !this.generating && !this.submitting)
                            .onSelect((index: number) => { void this.chooseBook(this.choices[index]); })
                        Select(this.chapterOptions()).value(this.selected.chapter_name).width('100%').enabled(!this.loading && !this.generating && !this.submitting)
                            .onSelect((index: number) => { this.chooseChapter(this.chapters[index]); })
                        Button(this.questions.length > 0 ? '再出一组' : '生成复习题').width('100%')
                            .enabled(!this.generating && !this.submitting && this.chapters.length > 0)
                            .onClick(() => { void this.startReview(); })
                    }
                    if (this.origin.chapter_name.length > 0) {
                        Text('本轮：' + this.origin.chapter_name).width('100%').fontColor($r('app.color.text_secondary'))
                    }
                    Text(this.statusText).width('100%').fontColor($r('app.color.text_secondary'))
                    if (this.generating) {
                        LoadingProgress().width(28).height(28)
                    }
                    if (this.errorText.length > 0) {
                        Text(this.errorText).width('100%').fontColor($r('app.color.text_danger'))
                        if (this.flowId.length > 0 && this.questions.length === 0) {
                            Button('重新同步').onClick(() => { void this.loadFlow(); })
                        } else if (this.choices.length === 0) {
                            Button('重新加载').onClick(() => { void this.loadChoices(); })
                        }
                    }
                    if (this.needsReading) {
                        Button('继续读这一章').width('100%').onClick(() => { this.onRead(this.origin, this.flowId); })
                    }
                    ForEach(this.questions, (question: ReviewQuestion, index: number) => {
                        Column({ space: 12 }) {
                            Text('第 ' + (index + 1) + ' 题').width('100%').fontColor($r('app.color.text_secondary'))
                            MarkdownView({ source: question.content || question.title }).width('100%')
                            if (this.options(question).length > 0) {
                                ForEach(this.options(question), (option: string) => {
                                    Button(option).width('100%').height('auto').padding(12)
                                        .backgroundColor(this.answers[index] === option ? $r('app.color.brand_soft') : $r('app.color.bg_sunken'))
                                        .fontColor($r('app.color.text_primary')).enabled(!this.submitted && !this.submitting)
                                        .onClick(() => { this.setAnswer(index, option); })
                                }, (option: string, optionIndex: number) => option + ':' + optionIndex)
                            } else {
                                TextArea({ text: this.answers[index] || '', placeholder: '写下你的想法' }).width('100%').height(110)
                                    .enabled(!this.submitted && !this.submitting).onChange((value: string) => { this.setAnswer(index, value); })
                            }
                            if (this.submitted && question.answer.length > 0) {
                                Text('参考答案').width('100%').fontColor($r('app.color.text_secondary'))
                                MarkdownView({ source: question.answer }).width('100%')
                            }
                        }.padding(16).width('100%').borderRadius(16).backgroundColor($r('app.color.bg_card'))
                    }, (question: ReviewQuestion, index: number) => this.questionId(question, index))
                    if (this.submitted) {
                        Text('本轮结果：' + this.resultText).fontSize(18).width('100%')
                        Button('回到时间线').width('100%').onClick(() => { this.onBack(); })
                    } else if (this.questions.length > 0) {
                        Button(this.submitting ? '正在提交…' : '提交作答').width('100%').enabled(!this.submitting)
                            .onClick(() => { void this.submit(); })
                    }
                }.width('100%').padding({ left: 16, right: 16, top: 8, bottom: 32 })
            }.layoutWeight(1).width('100%')
        }.width('100%').height('100%').backgroundColor($r('app.color.bg_page'))
    }
}

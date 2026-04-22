import type { CaseProfilePayload } from '../types';

export interface ConstitutionQuestion {
  id: string;
  constitution: string;
  prompt: string;
  hint: string;
}

export const CONSTITUTION_SCORE_FIELD_MAP = {
  平和: 'constitution_pinghe_score',
  气虚: 'constitution_qixu_score',
  阳虚: 'constitution_yangxu_score',
  阴虚: 'constitution_yinxu_score',
  痰湿: 'constitution_tanshi_score',
  湿热: 'constitution_shire_score',
  血瘀: 'constitution_xueyu_score',
  气郁: 'constitution_qiyu_score',
  特禀: 'constitution_tebing_score',
} as const;

export const CONSTITUTION_OPTIONS = Object.keys(CONSTITUTION_SCORE_FIELD_MAP);

export const QUESTIONNAIRE_OPTIONS = [
  { label: '从不', value: 1 },
  { label: '偶尔', value: 2 },
  { label: '有时', value: 3 },
  { label: '经常', value: 4 },
  { label: '总是', value: 5 },
];

export const CONSTITUTION_QUESTIONNAIRE: ConstitutionQuestion[] = [
  { id: 'pinghe_energy', constitution: '平和', prompt: '平时精力比较充沛，不容易疲惫。', hint: '偏向健康稳定底盘' },
  { id: 'pinghe_sleep', constitution: '平和', prompt: '整体睡眠、胃口、大小便都比较平稳。', hint: '看整体状态是否平和' },
  { id: 'qixu_fatigue', constitution: '气虚', prompt: '容易疲倦、少气懒言，活动后更明显。', hint: '常见于气虚倾向' },
  { id: 'qixu_cold', constitution: '气虚', prompt: '容易感冒或稍累就觉得撑不住。', hint: '看防御和恢复能力' },
  { id: 'yangxu_chill', constitution: '阳虚', prompt: '经常怕冷、手脚偏凉，喜欢热饮热食。', hint: '偏寒偏冷体感' },
  { id: 'yangxu_loose', constitution: '阳虚', prompt: '遇冷容易腹泻或清晨大便偏稀。', hint: '阳虚常见消化表现' },
  { id: 'yinxu_dry', constitution: '阴虚', prompt: '经常口干咽燥、手足心热或晚上更烦热。', hint: '偏燥偏热但不壮实' },
  { id: 'yinxu_sweat', constitution: '阴虚', prompt: '容易心烦、盗汗、睡觉时出汗或失眠。', hint: '阴液不足的常见线索' },
  { id: 'tanshi_heavy', constitution: '痰湿', prompt: '身体容易困重、头昏、胸闷或痰多。', hint: '湿浊偏重的典型感觉' },
  { id: 'tanshi_greasy', constitution: '痰湿', prompt: '体型偏胖、腹胀、油腻食物后更不舒服。', hint: '痰湿与运化差相关' },
  { id: 'shire_bitter', constitution: '湿热', prompt: '容易口苦口黏、尿黄、长痘或容易上火。', hint: '偏热偏湿的信号' },
  { id: 'shire_greasy', constitution: '湿热', prompt: '头面容易出油、闷热不爽、舌苔容易厚腻。', hint: '常见湿热外显表现' },
  { id: 'xueyu_fixed', constitution: '血瘀', prompt: '身体有固定刺痛、痛经有血块或面色晦暗。', hint: '瘀滞类表现' },
  { id: 'xueyu_dark', constitution: '血瘀', prompt: '容易出现暗沉、瘀青或局部长期不舒。', hint: '看瘀血倾向' },
  { id: 'qiyu_mood', constitution: '气郁', prompt: '常觉得情绪郁闷、胸胁不舒、容易叹气。', hint: '情志郁结倾向' },
  { id: 'qiyu_stress', constitution: '气郁', prompt: '压力一大就胃口差、睡不好或堵得慌。', hint: '压力与身体反应联动' },
  { id: 'tebing_allergy', constitution: '特禀', prompt: '容易过敏、鼻炎、荨麻疹或对特定食物敏感。', hint: '过敏体质线索' },
  { id: 'tebing_sensitive', constitution: '特禀', prompt: '季节变化或接触刺激物时，身体反应特别明显。', hint: '外界敏感度较高' },
];

export type ConstitutionQuestionnaireAnswers = Record<string, number>;

const normalizeScore = (values: number[]) => {
  if (!values.length) {
    return 0;
  }
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  return Math.round(((avg - 1) / 4) * 100);
};

export const hasQuestionnaireResult = (payload?: Partial<CaseProfilePayload> | null) =>
  Boolean(
    payload?.constitution_primary ||
    payload?.constitution_pinghe_score !== null && payload?.constitution_pinghe_score !== undefined ||
    payload?.constitution_qixu_score !== null && payload?.constitution_qixu_score !== undefined ||
    payload?.constitution_yangxu_score !== null && payload?.constitution_yangxu_score !== undefined ||
    payload?.constitution_yinxu_score !== null && payload?.constitution_yinxu_score !== undefined ||
    payload?.constitution_tanshi_score !== null && payload?.constitution_tanshi_score !== undefined ||
    payload?.constitution_shire_score !== null && payload?.constitution_shire_score !== undefined ||
    payload?.constitution_xueyu_score !== null && payload?.constitution_xueyu_score !== undefined ||
    payload?.constitution_qiyu_score !== null && payload?.constitution_qiyu_score !== undefined ||
    payload?.constitution_tebing_score !== null && payload?.constitution_tebing_score !== undefined
  );

export const buildQuestionnairePayload = (
  answers: ConstitutionQuestionnaireAnswers,
): Partial<CaseProfilePayload> => {
  const grouped = new Map<string, number[]>();
  CONSTITUTION_QUESTIONNAIRE.forEach((question) => {
    const answer = answers[question.id];
    if (!grouped.has(question.constitution)) {
      grouped.set(question.constitution, []);
    }
    if (typeof answer === 'number') {
      grouped.get(question.constitution)?.push(answer);
    }
  });

  const namedScores = CONSTITUTION_OPTIONS.map((constitution) => ({
    constitution,
    score: normalizeScore(grouped.get(constitution) || []),
  }));
  namedScores.sort((left, right) => right.score - left.score);

  const primary = namedScores[0]?.constitution || null;
  const secondary = namedScores
    .filter((item) => item.constitution !== primary && item.score >= 40)
    .slice(0, 2)
    .map((item) => item.constitution);

  const today = new Date().toISOString().slice(0, 10);
  const payload: Partial<CaseProfilePayload> = {
    constitution_primary: primary,
    constitution_secondary: secondary,
    constitution_assessed_at: today,
    constitution_reassessment_cycle_days: 90,
  };

  namedScores.forEach((item) => {
    const fieldName = CONSTITUTION_SCORE_FIELD_MAP[item.constitution as keyof typeof CONSTITUTION_SCORE_FIELD_MAP];
    payload[fieldName] = item.score;
  });

  return payload;
};

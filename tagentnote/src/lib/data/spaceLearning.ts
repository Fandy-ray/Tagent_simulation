export const spaceStages = {
	primary: {
		label: '小学',
		approach: '从故事和现象开始',
		description: '用生活里的例子认识航天，先看一看，再猜一猜。',
		answer:
			'想象你把球朝前扔。球一边往前飞，一边被地球往下拉。卫星也一样，只是它飞得很快，往前飞时地面也弯向下方，于是它就能绕着地球一直转。',
		task: '把卫星放到近一点和远一点的位置。看看哪颗卫星先绕完一圈。'
	},
	middle: {
		label: '初中',
		approach: '从图示理解原理',
		description: '观察运动方向和受力，用图解释航天现象。',
		answer:
			'卫星的速度方向沿着轨道的切线，地球引力则指向地心。引力持续改变速度的方向，使路径弯曲。在理想圆轨道上，引力与速度方向垂直，卫星的速率保持不变。',
		task: '把轨道升高，观察卫星绕行一圈的时间如何变化。'
	},
	high: {
		label: '高中',
		approach: '从变量和数据推理',
		description: '用模型比较结果，解释变化，并查阅原始资料。',
		answer:
			'把地球近似为球对称天体，忽略阻力。令万有引力等于圆周运动所需的向心力，得到 v = √(GM/r)，周期 T = 2π√(r³/GM)。这里的 r 是卫星到地心的距离，由地球半径与轨道高度相加得到。',
		task: '记录两个轨道高度下的速度和周期，验证半径变大时速度与周期的变化方向。'
	}
} as const;

export type SpaceStage = keyof typeof spaceStages;
export const stageKeys = Object.keys(spaceStages) as SpaceStage[];

export const orbitQuestion = '卫星为什么不会掉下来？';
export const orbitSource = {
	title: 'NASA · Gravity & Mechanics',
	href: 'https://science.nasa.gov/learn/basics-of-space-flight/chapter3-4/'
};

type Lesson = {
	id: string;
	title: string;
	explanation: string;
	options: [string, string];
	correct: number;
};
type Topic = { id: string; title: string; lessons: Lesson[] };

function lesson(
	id: string,
	title: string,
	explanation: string,
	options: [string, string],
	correct = 0
): Lesson {
	return { id, title, explanation, options, correct };
}

export const spaceTopics: Record<SpaceStage, Topic[]> = {
	primary: [
		{
			id: 'satellites',
			title: '跟着卫星看地球',
			lessons: [
				lesson('orbit', orbitQuestion, spaceStages.primary.answer, [
					'引力让卫星不断转弯',
					'太空里完全没有引力'
				]),
				lesson(
					'pictures',
					'卫星照片能看见什么？',
					'从高处拍摄，可以在一张图里看到大片地面。比较同一区域的照片，可以发现云团移动或河流周围的变化。',
					['比较同一地点的两张图', '只看照片的文件名']
				),
				lesson(
					'moon',
					'月亮也是卫星吗？',
					'月亮是绕地球运动的天然卫星。人造卫星由人设计和制造，也能绕地球运行。',
					['天然卫星', '人造卫星']
				)
			]
		},
		{
			id: 'station',
			title: '空间站的一天',
			lessons: [
				lesson(
					'floating',
					'为什么航天员看起来在漂浮？',
					'航天员和空间站一起绕地球运动，也一起下落。站内的物体和航天员一样运动，就好像浮了起来。',
					['人和空间站一起下落', '空间站挡住了引力']
				),
				lesson(
					'sleep',
					'在空间站睡觉会飘走吗？',
					'航天员可以用固定好的睡袋睡觉，避免在睡着时漂离原位。',
					['用固定的睡袋', '靠枕头压住身体']
				),
				lesson(
					'water',
					'水滴在空间站是什么形状？',
					'小水滴在空间站常呈球状。水表面的拉力会让水滴尽量缩小自己的表面积。',
					['接近球形', '一定是一片平的']
				)
			]
		}
	],
	middle: [
		{
			id: 'motion',
			title: '卫星的运动与受力',
			lessons: [
				lesson('orbit', orbitQuestion, spaceStages.middle.answer, [
					'沿轨道切线的是速度',
					'沿轨道切线的是引力'
				]),
				lesson(
					'gravity',
					'引力朝哪个方向？',
					'把地球近似为球体时，卫星受到的引力沿卫星与地心的连线指向地心。',
					['指向地心', '始终指向北方']
				),
				lesson(
					'period',
					'升高轨道，绕一圈会更快吗？',
					'在理想圆轨道下，更高的轨道走一圈更远，卫星的速度也更小，所以周期更长。',
					['周期变长', '周期变短']
				)
			]
		},
		{
			id: 'moonlight',
			title: '地月系统的光影',
			lessons: [
				lesson(
					'phases',
					'月亮为什么会有圆缺？',
					'太阳照亮月球的一半。随着月球绕地球运动，我们看到的亮面比例会改变。',
					['看到的亮面比例变了', '月球本身变小了']
				),
				lesson(
					'eclipse',
					'月食和普通月相有什么不同？',
					'月食发生时月球进入地球的影子。普通月相来自日、地、月的相对位置变化。',
					['月球进入地球的影子', '月球每晚都进入地球的影子']
				),
				lesson(
					'rotation',
					'为什么月球总以近似同一面朝向地球？',
					'月球自转一周和绕地球公转一周的时间相近，所以从地球主要看见它的同一面。',
					['自转与公转周期相近', '月球完全不自转']
				)
			]
		}
	],
	high: [
		{
			id: 'model',
			title: '圆轨道的定量模型',
			lessons: [
				lesson('orbit', orbitQuestion, spaceStages.high.answer, ['v = √(GM/r)', 'v = √(GMr)']),
				lesson(
					'speed',
					'轨道更高时，卫星的速度如何变化？',
					'在同一中心天体的圆轨道模型中，v 与 r 的平方根成反比。比较时应使用距地心的半径。',
					['速度减小', '速度增大']
				),
				lesson(
					'period',
					'怎样比较两条轨道的周期？',
					'同一中心天体的两个圆轨道满足 T₂/T₁ = (r₂/r₁) 的 3/2 次方。',
					['周期比取决于半径比', '两条圆轨道的周期必定相等']
				)
			]
		},
		{
			id: 'observations',
			title: '遥感观测与数据解读',
			lessons: [
				lesson(
					'resolution',
					'空间分辨率是什么意思？',
					'一个像元对应的地面范围越小，图像就越容易区分相邻的细节。',
					['对应的地面范围更小', '照片文件名更长']
				),
				lesson(
					'bands',
					'为什么要比较不同波段？',
					'同一种地物在不同波段的反射特性可以不同。比较波段有助于区分肉眼看起来相似的地物。',
					['不同波段能提供互补信息', '所有波段的反射一定相同']
				),
				lesson(
					'change',
					'两张图不同就能断定地表变了吗？',
					'应先检查拍摄季节、云量和光照等条件，再判断差异能否归因于地表变化。',
					['先排除观测条件差异', '有像素差异就一定是地表变化']
				)
			]
		}
	]
};

export function learningContext(params: Pick<URLSearchParams, 'get'>) {
	const stage = stageKeys.find((key) => key === params.get('space_stage'));
	const topic = stage && spaceTopics[stage].find((item) => item.id === params.get('space_topic'));
	if (!stage || !topic) return null;
	const lesson = topic.lessons.find((item) => item.id === params.get('space_lesson'));
	return { stage, topic, lesson };
}

export function learningContextParams(stage: SpaceStage, topic: string, lesson?: string) {
	const params = new URLSearchParams({ space_stage: stage, space_topic: topic });
	if (lesson) params.set('space_lesson', lesson);
	return params;
}

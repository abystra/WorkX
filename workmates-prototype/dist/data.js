export const initialData = {
  agents: [
    {id:'a1',name:'我的智能伙伴',description:'No description yet',tag:'Personal',avatar:0,tasks:17,skills:5},
    {id:'a2',name:'技术顾问',description:'解答软件开发与故障排查问题，评审系统架构，并讲解机器学习、大模型、RAG、Agent 等 AI 基础知识。',tag:'Team',avatar:1,tasks:0,skills:4},
    {id:'a3',name:'Codex 工作助手',description:'擅长代码开发、资料分析、技术方案、产品文档、汇报材料、项目规划及各类办公文件处理。',tag:'Third-party',avatar:2,tasks:0,skills:0},
    {id:'a4',name:'产品经理搭档',description:'帮助产品团队梳理需求、分析用户问题、规划产品路线并复盘交付，输出可执行的产品方案。',tag:'',avatar:3,tasks:1,skills:10},
    {id:'a5',name:'智能体小队',description:'工作空间的默认智能体小队，由队长统筹安排成员间的协作。',tag:'Squads',avatar:5,tasks:0,skills:1}
  ],
  tasks: [
    {id:'t1',name:'整理产品自动化测试方法说明草稿',date:'10/29 19:06',agent:'a1',status:'done'},
    {id:'t2',name:'创建周报自动生成编排技能',date:'10/29 17:54',agent:'a1',status:'done',unread:true},
    {id:'t3',name:'生成本周周报',date:'10/28 14:03',agent:'a1',status:'done'},
    {id:'t4',name:'咨询自定义 MCP Server 接入方法',date:'10/28 10:25',agent:'a1',status:'done'},
    {id:'t5',name:'通过搜索整理行业相关内容',date:'10/27 16:59',agent:'a1',status:'done'},
    {id:'t6',name:'了解智能伙伴的能力范围',date:'10/27 15:50',agent:'a1',status:'done'},
    {id:'t7',name:'总结昨日工作日报',date:'10/26 19:33',agent:'a1',status:'done'},
    {id:'t8',name:'撰写团队共享模板功能产品需求说明',date:'10/26 18:33',agent:'a4',status:'done'},
    {id:'t9',name:'查询近期周报',date:'10/25 18:37',agent:'a1',status:'done'},
    {id:'t10',name:'本周大模型与 Agent 技术动态调研',date:'10/24 19:28',agent:'a1',status:'done'}
  ],
  automations:[
    {id:'au1',name:'每周工作报告',description:'汇总本周完成的任务、关键成果和下周计划，生成一份结构清晰的周报。',schedule:'Every Friday at 17:00',enabled:true},
    {id:'au2',name:'每日行业资讯简报',description:'精选 AI 与产品设计领域的重要动态，整理值得关注的观点和趋势。',schedule:'Every weekday at 09:00',enabled:true},
    {id:'au3',name:'项目进度回顾',description:'梳理项目里程碑、交付进展与需要关注的风险。',schedule:'Every Monday at 10:00',enabled:false}
  ],
  projects:[
    {id:'p1',name:'产品体验升级',description:'探索更自然、高效的产品体验，让每个细节都恰到好处。',tasks:8,updated:'Today',color:'blue'},
    {id:'p2',name:'AI 工作流探索',description:'从真实场景出发，与智能伙伴共同构建下一代工作方式。',tasks:5,updated:'Yesterday',color:'purple'},
    {id:'p3',name:'团队知识库',description:'沉淀方法、共享经验，让好想法成为团队共同的财富。',tasks:3,updated:'Oct 27',color:'green'}
  ],
  library:[
    {id:'f1',name:'产品体验优化方案',type:'doc',updated:'Today'},
    {id:'f2',name:'团队季度项目汇报',type:'slides',updated:'Yesterday'},
    {id:'f3',name:'项目任务跟踪清单',type:'sheet',updated:'Oct 28'},
    {id:'f4',name:'智能伙伴使用指南',type:'doc',updated:'Oct 27'},
    {id:'f5',name:'AI 工作流设计提案',type:'slides',updated:'Oct 26'},
    {id:'f6',name:'产品需求优先级评估',type:'sheet',updated:'Oct 25'}
  ],
  hideQuick:false,proactive:false
};
initialData.tasks.forEach((task,index)=>{task.project=['p1','p2','p3','p2','p1','p3','p3','p1','p3','p2'][index];});
initialData.projects.forEach(project=>{project.tasks=initialData.tasks.filter(task=>task.project===project.id).length;});
export const suggestions = [
  {agent:'a1',label:'Slides',icon:'file',text:'基于项目的当前进展与后续计划，生成一份项目汇报 PPT，包含背景、技术方案与下一步计划。'},
  {agent:'a4',label:'Product Prototype',icon:'grid',text:'为“团队共享模板”功能撰写产品需求说明，包含场景、范围、流程和验收标准。'},
  {agent:'a1',label:'Deep Research',icon:'globe',text:'调研主流知识库产品的来源材料展示与预览方案，对比不同方案的技术成本与用户体验。'},
  {agent:'a1',label:'消息整理',icon:'chat',text:'整理今天的工作消息，提炼重要事项和需要跟进的行动。'},
  {agent:'a1',label:'文档总结',icon:'file',text:'梳理团队知识库里的产品文档，帮我总结关键结论和待办。'},
  {agent:'a2',label:'Code',icon:'code',text:'评审当前项目的技术架构，整理一份可以落地的优化建议。'}
];

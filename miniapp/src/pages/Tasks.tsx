import { useState, useEffect, useCallback } from 'react';
import { useTelegram } from '../hooks/useTelegram';
import { getTasks, claimTask, claimAllTasks, TaskItem, TasksData } from '../services/api';

type TaskType = 'daily' | 'weekly' | 'monthly';

const TYPE_NAMES: Record<TaskType, string> = {
  daily: '每日',
  weekly: '每周',
  monthly: '每月',
};

export function Tasks() {
  const { hapticFeedback, showAlert } = useTelegram();
  const [taskType, setTaskType] = useState<TaskType>('daily');
  const [tasksData, setTasksData] = useState<TasksData | null>(null);
  const [loading, setLoading] = useState(true);
  const [claimingAll, setClaimingAll] = useState(false);
  const [claimingTask, setClaimingTask] = useState<string | null>(null);

  const loadTasks = useCallback(async (type: TaskType) => {
    setLoading(true);
    const response = await getTasks(type);
    if (response.status === 'ok' && response.data) {
      setTasksData(response.data);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadTasks(taskType);
  }, [taskType, loadTasks]);

  const handleClaimTask = async (task: TaskItem) => {
    if (!task.is_claimable || claimingTask) return;

    setClaimingTask(task.task_id);
    hapticFeedback('medium');

    const response = await claimTask(task.task_id);
    
    if (response.status === 'ok' && response.data) {
      if (response.data.success) {
        hapticFeedback('heavy');
        showAlert(response.data.message);
        loadTasks(taskType);
      } else {
        showAlert(response.data.message);
      }
    } else {
      showAlert(response.message || '领取失败');
    }
    
    setClaimingTask(null);
  };

  const handleClaimAll = async () => {
    if (!tasksData?.summary.claimable || claimingAll) return;

    setClaimingAll(true);
    hapticFeedback('medium');

    const response = await claimAllTasks();
    
    if (response.status === 'ok' && response.data) {
      if (response.data.success) {
        hapticFeedback('heavy');
        showAlert(response.data.message);
        loadTasks(taskType);
      } else {
        showAlert(response.data.message);
      }
    } else {
      showAlert(response.message || '领取失败');
    }
    
    setClaimingAll(false);
  };

  const renderTaskItem = (task: TaskItem) => {
    // 状态图标
    let statusIcon = '⬜';
    if (task.reward_claimed) {
      statusIcon = '✅';
    } else if (task.completed) {
      statusIcon = '🎁';
    }

    return (
      <div 
        key={task.task_id}
        className="flex items-center gap-3 p-3 bg-tg-secondary-bg rounded-xl"
      >
        {/* 图标 */}
        <div className="text-2xl">{task.icon}</div>
        
        {/* 内容 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-tg-text truncate">{task.name}</span>
            {task.is_bonus && (
              <span className="text-xs bg-yellow-500/20 text-yellow-600 px-1.5 py-0.5 rounded">额外</span>
            )}
          </div>
          
          {/* 进度条 */}
          <div className="mt-1.5">
            <div className="flex items-center justify-between text-xs text-tg-hint mb-1">
              <span>{task.progress}/{task.target}</span>
              <span>+{task.reward_points}积分</span>
            </div>
            <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div 
                className={`h-full rounded-full transition-all ${
                  task.completed ? 'bg-green-500' : 'bg-tg-button'
                }`}
                style={{ width: `${task.progress_percent}%` }}
              />
            </div>
          </div>
        </div>
        
        {/* 状态/领取按钮 */}
        <div className="flex-shrink-0">
          {task.is_claimable ? (
            <button
              onClick={() => handleClaimTask(task)}
              disabled={claimingTask === task.task_id}
              className="px-3 py-1.5 bg-tg-button text-tg-button-text text-sm rounded-lg active:scale-95 transition-transform disabled:opacity-50"
            >
              {claimingTask === task.task_id ? '...' : '领取'}
            </button>
          ) : (
            <span className="text-xl">{statusIcon}</span>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="p-4 pb-20">
      {/* 任务类型切换 */}
      <div className="flex gap-2 mb-4">
        {(['daily', 'weekly', 'monthly'] as TaskType[]).map((type) => (
          <button
            key={type}
            onClick={() => setTaskType(type)}
            className={`flex-1 py-2 rounded-xl text-sm font-medium transition-all ${
              taskType === type
                ? 'bg-tg-button text-tg-button-text'
                : 'bg-tg-secondary-bg text-tg-hint'
            }`}
          >
            {TYPE_NAMES[type]}
          </button>
        ))}
      </div>

      {/* 统计卡片 */}
      {tasksData && (
        <div className="card mb-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-tg-hint">
                {TYPE_NAMES[taskType]}任务进度
              </div>
              <div className="text-2xl font-bold text-tg-text mt-1">
                {tasksData.summary.completed}/{tasksData.summary.total}
              </div>
            </div>
            
            {tasksData.summary.claimable > 0 && (
              <button
                onClick={handleClaimAll}
                disabled={claimingAll}
                className="px-4 py-2 bg-green-500 text-white rounded-xl font-medium active:scale-95 transition-transform disabled:opacity-50"
              >
                {claimingAll ? '领取中...' : `一键领取 +${tasksData.summary.claimable_points}`}
              </button>
            )}
          </div>
        </div>
      )}

      {/* 任务列表 */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="w-8 h-8 border-4 border-tg-button border-t-transparent rounded-full animate-spin" />
        </div>
      ) : tasksData?.tasks.length ? (
        <div className="space-y-2">
          {tasksData.tasks.map(renderTaskItem)}
        </div>
      ) : (
        <div className="text-center text-tg-hint py-8">
          暂无任务
        </div>
      )}
    </div>
  );
}

import { useState, useEffect } from 'react';
import { getCheckinCalendar, CalendarRecord } from '../services/api';

interface CheckinCalendarProps {
  onMonthChange?: (year: number, month: number) => void;
}

export function CheckinCalendar({ onMonthChange }: CheckinCalendarProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [records, setRecords] = useState<CalendarRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth() + 1;

  useEffect(() => {
    loadCalendar();
    onMonthChange?.(year, month);
  }, [year, month, onMonthChange]);

  const loadCalendar = async () => {
    setLoading(true);
    const monthStr = `${year}-${month.toString().padStart(2, '0')}`;
    const response = await getCheckinCalendar(monthStr);
    if (response.status === 'ok' && response.data) {
      setRecords(response.data.records);
    }
    setLoading(false);
  };

  const goToPrevMonth = () => {
    setCurrentDate(new Date(year, month - 2, 1));
  };

  const goToNextMonth = () => {
    const now = new Date();
    const nextMonth = new Date(year, month, 1);
    if (nextMonth <= now) {
      setCurrentDate(nextMonth);
    }
  };

  // 获取本月第一天是星期几
  const firstDayOfMonth = new Date(year, month - 1, 1).getDay();
  
  // 获取本月天数
  const daysInMonth = new Date(year, month, 0).getDate();
  
  // 创建日历格子
  const days: (number | null)[] = [];
  
  // 填充空白
  for (let i = 0; i < firstDayOfMonth; i++) {
    days.push(null);
  }
  
  // 填充日期
  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }

  // 检查某天是否签到
  const getRecordForDay = (day: number): CalendarRecord | undefined => {
    const dateStr = `${year}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
    return records.find(r => r.date === dateStr);
  };

  const isToday = (day: number): boolean => {
    const now = new Date();
    return year === now.getFullYear() && month === now.getMonth() + 1 && day === now.getDate();
  };

  const weekDays = ['日', '一', '二', '三', '四', '五', '六'];

  return (
    <div className="card">
      {/* 月份切换 */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={goToPrevMonth}
          className="p-2 text-tg-link active:opacity-70"
        >
          ◀
        </button>
        <span className="text-lg font-medium">{year}年{month}月</span>
        <button
          onClick={goToNextMonth}
          className="p-2 text-tg-link active:opacity-70"
          disabled={new Date(year, month, 1) > new Date()}
        >
          ▶
        </button>
      </div>

      {/* 星期标题 */}
      <div className="grid grid-cols-7 gap-1 mb-2">
        {weekDays.map(day => (
          <div key={day} className="text-center text-xs text-tg-hint py-1">
            {day}
          </div>
        ))}
      </div>

      {/* 日期格子 */}
      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-tg-button border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-7 gap-1">
          {days.map((day, index) => {
            if (day === null) {
              return <div key={`empty-${index}`} className="aspect-square" />;
            }

            const record = getRecordForDay(day);
            const today = isToday(day);

            return (
              <div
                key={day}
                className={`aspect-square flex flex-col items-center justify-center rounded-lg text-sm
                  ${today ? 'ring-2 ring-tg-button' : ''}
                  ${record ? 'bg-tg-button/20 text-tg-button' : 'text-tg-text'}
                `}
              >
                <span className={today ? 'font-bold' : ''}>{day}</span>
                {record && (
                  <span className="text-[10px]">
                    {record.is_lucky ? '🍀' : '✓'}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 统计 */}
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-center text-sm text-tg-hint">
        本月签到 <span className="text-tg-button font-medium">{records.length}</span> 天
      </div>
    </div>
  );
}

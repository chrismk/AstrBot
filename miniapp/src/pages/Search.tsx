import { useState, useEffect, useCallback } from 'react';
import { useTelegram } from '../hooks/useTelegram';
import {
  search,
  getHotSearches,
  SearchData,
  BookResult,
  MusicResult,
  DoubanResult,
  PansouResult,
  HotSearchItem,
} from '../services/api';

type SearchType = 'book' | 'music' | 'douban' | 'pansou';

const SEARCH_TYPES: { type: SearchType; label: string; icon: string }[] = [
  { type: 'book', label: '书籍', icon: '📚' },
  { type: 'music', label: '音乐', icon: '🎵' },
  { type: 'douban', label: '豆瓣', icon: '⭐' },
  { type: 'pansou', label: '网盘', icon: '📁' },
];

const MUSIC_PLATFORMS = [
  { id: 'qq', name: 'QQ音乐' },
  { id: 'netease', name: '网易云' },
  { id: 'kugou', name: '酷狗' },
];

const DOUBAN_TYPES = [
  { id: 'book', name: '书籍' },
  { id: 'movie', name: '电影' },
];

const CLOUD_TYPES = [
  { id: '', name: '全部' },
  { id: 'baidu', name: '百度网盘' },
  { id: 'quark', name: '夸克' },
  { id: 'ali', name: '阿里云' },
  { id: '115', name: '115' },
];

// 网盘类型图标映射
const CLOUD_TYPE_ICONS: { [key: string]: string } = {
  baidu: '🟡',
  quark: '🟣',
  ali: '🟠',
  '115': '🔵',
  unknown: '📁',
};

export function Search() {
  const { hapticFeedback } = useTelegram();
  const [searchType, setSearchType] = useState<SearchType>('book');
  const [query, setQuery] = useState('');
  const [platform, setPlatform] = useState('qq');
  const [doubanType, setDoubanType] = useState<'book' | 'movie'>('book');
  const [cloudType, setCloudType] = useState('');
  const [searchData, setSearchData] = useState<SearchData | null>(null);
  const [hotSearches, setHotSearches] = useState<{ [key: string]: HotSearchItem[] }>({});
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // 加载热搜
  const loadHotSearches = useCallback(async () => {
    const response = await getHotSearches();
    if (response.status === 'ok' && response.data) {
      setHotSearches(response.data.hot_searches);
    }
  }, []);

  useEffect(() => {
    loadHotSearches();
  }, [loadHotSearches]);

  // 执行搜索
  const handleSearch = async (q?: string, page: number = 1) => {
    const searchQuery = q ?? query;
    if (!searchQuery.trim()) return;

    if (page === 1) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    hapticFeedback('light');

    const response = await search(
      searchType,
      searchQuery,
      page,
      20,
      searchType === 'music' ? platform : undefined,
      searchType === 'douban' ? doubanType : undefined,
      searchType === 'pansou' ? cloudType : undefined
    );

    if (response.status === 'ok' && response.data) {
      if (page === 1) {
        setSearchData(response.data);
      } else if (searchData) {
        // 追加结果
        setSearchData({
          ...response.data,
          results: [...searchData.results, ...response.data.results],
        });
      }
    }

    setLoading(false);
    setLoadingMore(false);
  };

  // 点击热搜
  const handleHotClick = (keyword: string) => {
    setQuery(keyword);
    handleSearch(keyword);
  };

  // 加载更多
  const handleLoadMore = () => {
    if (searchData && searchData.pagination.has_more && !loadingMore) {
      handleSearch(query, searchData.pagination.page + 1);
    }
  };

  // 切换搜索类型
  const handleTypeChange = (type: SearchType) => {
    setSearchType(type);
    setSearchData(null);
  };

  // 格式化文件大小
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // 格式化时长
  const formatDuration = (seconds: number) => {
    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;
    return `${min}:${sec.toString().padStart(2, '0')}`;
  };

  // 渲染书籍结果
  const renderBookItem = (book: BookResult) => (
    <div key={book.id} className="flex gap-3 p-3 bg-tg-secondary-bg rounded-xl">
      <div className="text-3xl">📖</div>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-tg-text line-clamp-2">{book.title}</div>
        {book.author && (
          <div className="text-xs text-tg-hint mt-1">{book.author}</div>
        )}
        <div className="flex items-center gap-2 mt-1 text-xs text-tg-hint">
          {book.extension && <span className="uppercase">{book.extension}</span>}
          {book.filesize > 0 && <span>{formatSize(book.filesize)}</span>}
        </div>
      </div>
    </div>
  );

  // 渲染音乐结果
  const renderMusicItem = (song: MusicResult) => (
    <div key={song.id} className="flex gap-3 p-3 bg-tg-secondary-bg rounded-xl">
      {song.cover ? (
        <img
          src={song.cover}
          alt=""
          className="w-12 h-12 rounded-lg object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      ) : (
        <div className="w-12 h-12 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xl">
          🎵
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-tg-text truncate">{song.title}</div>
        <div className="text-xs text-tg-hint mt-0.5 truncate">{song.artist}</div>
        {song.album && (
          <div className="text-xs text-tg-hint truncate">{song.album}</div>
        )}
      </div>
      {song.duration > 0 && (
        <div className="text-xs text-tg-hint self-center">
          {formatDuration(song.duration)}
        </div>
      )}
    </div>
  );

  // 渲染豆瓣结果
  const renderDoubanItem = (item: DoubanResult) => (
    <a
      key={item.id}
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex gap-3 p-3 bg-tg-secondary-bg rounded-xl"
    >
      {item.cover ? (
        <img
          src={item.cover}
          alt=""
          className="w-12 h-16 rounded-lg object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      ) : (
        <div className="w-12 h-16 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xl">
          {item.douban_type === 'movie' ? '🎬' : '📖'}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-tg-text line-clamp-1">{item.title}</div>
        {item.rating > 0 && (
          <div className="flex items-center gap-1 mt-1">
            <span className="text-yellow-500">⭐</span>
            <span className="text-sm text-tg-text">{item.rating}</span>
            <span className="text-xs text-tg-hint">({item.rating_count}人)</span>
          </div>
        )}
        <div className="text-xs text-tg-hint mt-1 line-clamp-1">
          {item.douban_type === 'book' ? (
            <>{item.author?.join(', ')} {item.publisher && `/ ${item.publisher}`}</>
          ) : (
            <>{item.director?.join(', ')} {item.actors?.slice(0, 3).join(', ')}</>
          )}
          {item.year && ` / ${item.year}`}
        </div>
      </div>
    </a>
  );

  // 渲染网盘结果
  const renderPansouItem = (item: PansouResult, index: number) => (
    <div key={`${item.url}-${index}`} className="p-3 bg-tg-secondary-bg rounded-xl">
      <div className="flex items-start gap-2">
        <span className="text-lg">{CLOUD_TYPE_ICONS[item.cloud_type] || CLOUD_TYPE_ICONS.unknown}</span>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-tg-text line-clamp-2">
            {item.title || item.note || '未命名资源'}
          </div>
          {item.content && (
            <div className="text-xs text-tg-hint mt-1 line-clamp-2">{item.content}</div>
          )}
          <div className="flex items-center gap-2 mt-2 text-xs text-tg-hint">
            <span className="px-1.5 py-0.5 bg-tg-bg rounded">{item.cloud_type}</span>
            {item.source && <span>{item.source}</span>}
            {item.datetime && <span>{item.datetime}</span>}
          </div>
        </div>
      </div>
      <div className="mt-2 flex gap-2">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 py-1.5 text-center bg-tg-button text-tg-button-text rounded-lg text-sm"
        >
          打开链接
        </a>
        {item.password && (
          <button
            onClick={() => {
              navigator.clipboard.writeText(item.password);
              hapticFeedback('light');
            }}
            className="px-3 py-1.5 bg-tg-secondary-bg border border-tg-hint/20 text-tg-text rounded-lg text-sm"
          >
            密码: {item.password}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-4 pb-20">
      {/* 搜索框 */}
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder={`搜索${SEARCH_TYPES.find(t => t.type === searchType)?.label || ''}...`}
          className="flex-1 px-4 py-2.5 bg-tg-secondary-bg rounded-xl text-tg-text placeholder-tg-hint outline-none focus:ring-2 focus:ring-tg-button/50"
        />
        <button
          onClick={() => handleSearch()}
          disabled={loading || !query.trim()}
          className="px-4 py-2.5 bg-tg-button text-tg-button-text rounded-xl font-medium disabled:opacity-50"
        >
          {loading ? '...' : '搜索'}
        </button>
      </div>

      {/* 搜索类型切换 */}
      <div className="flex gap-2 mb-4">
        {SEARCH_TYPES.map(({ type, label, icon }) => (
          <button
            key={type}
            onClick={() => handleTypeChange(type)}
            className={`flex-1 py-2 rounded-xl text-sm font-medium transition-all ${
              searchType === type
                ? 'bg-tg-button text-tg-button-text'
                : 'bg-tg-secondary-bg text-tg-hint'
            }`}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* 音乐平台选择 */}
      {searchType === 'music' && (
        <div className="flex gap-2 mb-4">
          {MUSIC_PLATFORMS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPlatform(p.id)}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all ${
                platform === p.id
                  ? 'bg-tg-button/20 text-tg-button'
                  : 'bg-tg-secondary-bg text-tg-hint'
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}

      {/* 豆瓣类型选择 */}
      {searchType === 'douban' && (
        <div className="flex gap-2 mb-4">
          {DOUBAN_TYPES.map((t) => (
            <button
              key={t.id}
              onClick={() => setDoubanType(t.id as 'book' | 'movie')}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all ${
                doubanType === t.id
                  ? 'bg-tg-button/20 text-tg-button'
                  : 'bg-tg-secondary-bg text-tg-hint'
              }`}
            >
              {t.name}
            </button>
          ))}
        </div>
      )}

      {/* 网盘类型选择 */}
      {searchType === 'pansou' && (
        <div className="flex flex-wrap gap-2 mb-4">
          {CLOUD_TYPES.map((t) => (
            <button
              key={t.id}
              onClick={() => setCloudType(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all ${
                cloudType === t.id
                  ? 'bg-tg-button/20 text-tg-button'
                  : 'bg-tg-secondary-bg text-tg-hint'
              }`}
            >
              {t.name}
            </button>
          ))}
        </div>
      )}

      {/* 搜索结果 */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="w-8 h-8 border-4 border-tg-button border-t-transparent rounded-full animate-spin" />
        </div>
      ) : searchData ? (
        <div>
          <div className="text-sm text-tg-hint mb-3">
            找到 {searchData.pagination.total} 个结果
          </div>
          <div className="space-y-2">
            {searchData.results.map((item, index) => {
              switch (searchType) {
                case 'book':
                  return renderBookItem(item as BookResult);
                case 'music':
                  return renderMusicItem(item as MusicResult);
                case 'douban':
                  return renderDoubanItem(item as DoubanResult);
                case 'pansou':
                  return renderPansouItem(item as PansouResult, index);
                default:
                  return null;
              }
            })}
          </div>

          {/* 加载更多 */}
          {searchData.pagination.has_more && (
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="w-full mt-4 py-2.5 bg-tg-secondary-bg text-tg-hint rounded-xl text-sm"
            >
              {loadingMore ? '加载中...' : '加载更多'}
            </button>
          )}
        </div>
      ) : (
        /* 热搜推荐 */
        <div>
          {(hotSearches[searchType] || []).length > 0 && (
            <div>
              <div className="text-sm font-medium text-tg-hint mb-3">🔥 热门搜索</div>
              <div className="flex flex-wrap gap-2">
                {hotSearches[searchType]?.map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleHotClick(item.keyword)}
                    className="px-3 py-1.5 bg-tg-secondary-bg text-tg-text rounded-lg text-sm"
                  >
                    {item.keyword}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 空状态 */}
          {!(hotSearches[searchType] || []).length && (
            <div className="text-center py-12">
              <div className="text-4xl mb-3">🔍</div>
              <div className="text-tg-hint">输入关键词开始搜索</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

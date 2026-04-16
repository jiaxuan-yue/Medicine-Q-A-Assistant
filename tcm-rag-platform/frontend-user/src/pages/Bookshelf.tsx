import React, { useDeferredValue, useEffect, useState } from 'react';
import { Button, Empty, Input, Layout, message } from 'antd';
import {
  ArrowLeftOutlined,
  BookOutlined,
  CopyOutlined,
  DownOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  ANCIENT_BOOKS,
  BOOK_CATEGORY_COUNTS,
  BOOK_CATEGORY_ORDER,
  type AncientBook,
  type AncientBookCategory,
} from '../data/ancientBooks';
import './Bookshelf.css';

const { Header, Content } = Layout;

const ALL_CATEGORY = '全部馆藏';

const SPINE_PALETTES = [
  ['#4b2d1c', '#8b5a31', '#e5c07b'],
  ['#17392f', '#2f6b57', '#b9d3c3'],
  ['#40211f', '#7d3e34', '#f0c4a8'],
  ['#28314f', '#54648f', '#d6dff6'],
  ['#5c4317', '#aa7b24', '#f8dfa7'],
  ['#2c2340', '#5d4c89', '#d6cef5'],
];

const BOOK_SPINE_HEIGHT = 222;
const BOOK_SPINE_SINGLE_COLUMN_LIMIT = 11;

const paletteFor = (bookId: number) => SPINE_PALETTES[bookId % SPINE_PALETTES.length];

const computeShelfRowSize = (width: number) => {
  if (width < 520) {
    return 5;
  }
  if (width < 680) {
    return 6;
  }
  if (width < 860) {
    return 8;
  }
  if (width < 1024) {
    return 10;
  }
  if (width < 1280) {
    return 12;
  }
  return 14;
};

const matchBook = (book: AncientBook, keyword: string) => {
  if (!keyword) {
    return true;
  }

  const sequence = String(book.id).padStart(3, '0');
  const haystack = `${book.title} ${book.filename} ${book.category} ${sequence}`.toLowerCase();
  return haystack.includes(keyword);
};

const splitTitleColumns = (title: string) => {
  const characters = Array.from(title.replace(/\s+/g, '').trim());
  if (characters.length <= BOOK_SPINE_SINGLE_COLUMN_LIMIT) {
    return [characters.join('')];
  }

  const midpoint = Math.ceil(characters.length / 2);
  return [
    characters.slice(0, midpoint).join(''),
    characters.slice(midpoint).join(''),
  ];
};

const chunkBooks = (books: AncientBook[], chunkSize: number) => {
  const rows: AncientBook[][] = [];
  for (let index = 0; index < books.length; index += chunkSize) {
    rows.push(books.slice(index, index + chunkSize));
  }
  return rows;
};

const Bookshelf: React.FC = () => {
  const navigate = useNavigate();
  const [searchText, setSearchText] = useState('');
  const [activeCategory, setActiveCategory] = useState<typeof ALL_CATEGORY | AncientBookCategory>(ALL_CATEGORY);
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({});
  const [shelfRowSize, setShelfRowSize] = useState(() =>
    typeof window === 'undefined' ? 12 : computeShelfRowSize(window.innerWidth),
  );
  const deferredSearch = useDeferredValue(searchText.trim().toLowerCase());

  useEffect(() => {
    const handleResize = () => {
      setShelfRowSize(computeShelfRowSize(window.innerWidth));
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const filteredBooks = ANCIENT_BOOKS.filter((book) => {
    if (activeCategory !== ALL_CATEGORY && book.category !== activeCategory) {
      return false;
    }
    return matchBook(book, deferredSearch);
  });

  const sections = BOOK_CATEGORY_ORDER.map((category) => ({
    category,
    books: filteredBooks.filter((book) => book.category === category),
  })).filter((section) => section.books.length > 0);

  const handleCopy = async (book: AncientBook) => {
    try {
      await navigator.clipboard.writeText(book.title);
      message.success(`已复制《${book.title}》`);
    } catch {
      message.info(`请手动复制：${book.title}`);
    }
  };

  const toggleCategory = (category: AncientBookCategory) => {
    setCollapsedCategories((current) => ({
      ...current,
      [category]: !current[category],
    }));
  };

  return (
    <Layout className="bookshelf-layout">
      <Header className="bookshelf-header">
        <div className="bookshelf-brand">
          <div className="bookshelf-brand-mark">藏</div>
          <div className="bookshelf-brand-copy">
            <strong>古籍书架</strong>
            <span>700+ 册中医馆藏总览</span>
          </div>
        </div>
        <Button
          className="bookshelf-back"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/chats')}
        >
          返回问答首页
        </Button>
      </Header>

      <Content className="bookshelf-content">
        <section className="bookshelf-hero">
          <div className="bookshelf-hero-copy">
            <div className="section-badge">Ancient Collection Hall</div>
            <h1>把 700 册医籍，排成一座可以浏览的藏书楼。</h1>
            <p>
              这里收拢了当前项目接入的全部古籍目录。你可以按书名、编号、类别快速检索，
              也可以直接点一本书脊复制书名，回到问答页继续提问。
            </p>
            <div className="bookshelf-stats">
              <div className="bookshelf-stat">
                <span>馆藏总数</span>
                <strong>{ANCIENT_BOOKS.length}</strong>
              </div>
              <div className="bookshelf-stat">
                <span>分类维度</span>
                <strong>{BOOK_CATEGORY_ORDER.length}</strong>
              </div>
              <div className="bookshelf-stat">
                <span>建议动作</span>
                <strong>点书脊复制</strong>
              </div>
            </div>
          </div>

          <div className="bookshelf-hero-panel">
            <div className="bookshelf-search-card">
              <label htmlFor="bookshelf-search">搜索馆藏</label>
              <Input
                id="bookshelf-search"
                size="large"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="输入书名、编号、文件名或类别"
                prefix={<SearchOutlined />}
                allowClear
              />
              <div className="bookshelf-search-hint">
                <BookOutlined />
                <span>例：本草纲目 / 013 / 医案 / 伤寒</span>
              </div>
            </div>

            <div className="bookshelf-tip-card">
              <strong>使用方式</strong>
              <p>点击书脊即可复制准确书名，然后返回问答页，用“《书名》里怎么说……”继续问。</p>
              <Button
                className="bookshelf-tip-action"
                icon={<CopyOutlined />}
                onClick={() => navigate('/chats')}
              >
                带着书名去提问
              </Button>
            </div>
          </div>
        </section>

        <section className="bookshelf-filter-bar">
          <button
            type="button"
            className={`bookshelf-filter ${activeCategory === ALL_CATEGORY ? 'is-active' : ''}`}
            onClick={() => setActiveCategory(ALL_CATEGORY)}
          >
            <span>{ALL_CATEGORY}</span>
            <strong>{ANCIENT_BOOKS.length}</strong>
          </button>
          {BOOK_CATEGORY_ORDER.map((category) => (
            <button
              key={category}
              type="button"
              className={`bookshelf-filter ${activeCategory === category ? 'is-active' : ''}`}
              onClick={() => setActiveCategory(category)}
            >
              <span>{category}</span>
              <strong>{BOOK_CATEGORY_COUNTS[category]}</strong>
            </button>
          ))}
        </section>

        <section className="bookshelf-result-head">
          <div>
            <strong>当前展示 {filteredBooks.length} 册</strong>
            <span>
              {activeCategory === ALL_CATEGORY ? '浏览全部馆藏' : `正在查看：${activeCategory}`}
            </span>
          </div>
          <p>木色书脊只是视觉分组，不代表古籍原始版本或真实装帧。</p>
        </section>

        {sections.length === 0 ? (
          <div className="bookshelf-empty">
            <Empty description="没有找到匹配的古籍，换个书名或类别再试试。" />
          </div>
        ) : (
          sections.map((section) => {
            const collapsed = Boolean(collapsedCategories[section.category]);
            const rows = chunkBooks(section.books, shelfRowSize);

            return (
              <section
                key={section.category}
                className={`bookshelf-section ${collapsed ? 'is-collapsed' : ''}`}
              >
                <div className="bookshelf-section-head">
                  <div>
                    <h2>{section.category}</h2>
                    <p>{section.books.length} 册</p>
                  </div>
                  <button
                    type="button"
                    className="bookshelf-section-toggle"
                    onClick={() => toggleCategory(section.category)}
                  >
                    {collapsed ? <RightOutlined /> : <DownOutlined />}
                    <span>{collapsed ? '展开这一层' : '收起这一层'}</span>
                  </button>
                </div>

                {!collapsed && (
                  <div className="bookshelf-shelf">
                    <div className="bookshelf-stack">
                      {rows.map((row, rowIndex) => (
                        <div key={`${section.category}-${rowIndex}`} className="bookshelf-row">
                          <div
                            className="bookshelf-row-grid"
                            style={{ '--row-columns': row.length } as React.CSSProperties}
                          >
                            {row.map((book) => {
                              const [start, end, accent] = paletteFor(book.id);
                              const titleColumns = splitTitleColumns(book.title);
                              const isTwoColumn = titleColumns.length > 1;

                              return (
                                <button
                                  key={book.filename}
                                  type="button"
                                  className="book-spine"
                                  title={`${String(book.id).padStart(3, '0')} · ${book.title}`}
                                  style={
                                    {
                                      '--spine-start': start,
                                      '--spine-end': end,
                                      '--spine-accent': accent,
                                      '--spine-height': `${BOOK_SPINE_HEIGHT}px`,
                                    } as React.CSSProperties
                                  }
                                  onClick={() => handleCopy(book)}
                                >
                                  <span className="book-spine-index">
                                    {String(book.id).padStart(3, '0')}
                                  </span>
                                  <span className={`book-spine-title ${isTwoColumn ? 'is-two-column' : ''}`}>
                                    {titleColumns.map((column, index) => (
                                      <span key={`${book.filename}-${index}`} className="book-spine-title-column">
                                        {column}
                                      </span>
                                    ))}
                                  </span>
                                  <span className="book-spine-foot">{book.category}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            );
          })
        )}
      </Content>
    </Layout>
  );
};

export default Bookshelf;

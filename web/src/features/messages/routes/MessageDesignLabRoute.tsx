import { useMemo, useState } from 'react';
import './messagesLab.css';

type DesignMode = 'workspace' | 'canvas' | 'drawer';
type PreviewMode = 'desktop' | 'mobile';
type FilterMode = 'all' | 'unread' | 'groups';

type TrackAttachment = {
  title: string;
  artist: string;
  album: string;
  color: string;
};

type Message = {
  id: string;
  sender: 'you' | 'other' | 'system';
  author: string;
  body: string;
  time: string;
  track?: TrackAttachment;
};

type Conversation = {
  id: string;
  title: string;
  subtitle: string;
  kind: 'dm' | 'group';
  members: string[];
  unread: number;
  status: string;
  accent: string;
  mood: string;
  page: string;
  messages: Message[];
  queue: TrackAttachment[];
};

const TRACK_LIBRARY: TrackAttachment[] = [
  { title: 'So What', artist: 'Miles Davis', album: 'Kind of Blue', color: '#38bdf8' },
  { title: 'Genesis', artist: 'Justice', album: 'Cross', color: '#fb7185' },
  { title: 'Teardrop', artist: 'Massive Attack', album: 'Mezzanine', color: '#f59e0b' },
];

const INITIAL_CONVERSATIONS: Conversation[] = [
  {
    id: 'ava',
    title: 'Ava',
    subtitle: 'sent a track and wants a closer',
    kind: 'dm',
    members: ['You', 'Ava'],
    unread: 2,
    status: 'last active 2m ago',
    accent: '#f97316',
    mood: 'Molten orange',
    page: 'Profile',
    messages: [
      { id: 'ava-1', sender: 'other', author: 'Ava', body: 'Need something warmer after the opener.', time: '7:18 PM' },
      {
        id: 'ava-2',
        sender: 'other',
        author: 'Ava',
        body: 'This one lands perfectly.',
        time: '7:19 PM',
        track: TRACK_LIBRARY[0],
      },
      { id: 'ava-3', sender: 'you', author: 'You', body: 'That bassline buys us room. I am in.', time: '7:20 PM' },
    ],
    queue: [TRACK_LIBRARY[0], TRACK_LIBRARY[2]],
  },
  {
    id: 'crate-society',
    title: 'Neon Crate Society',
    subtitle: 'group sequencing tonight',
    kind: 'group',
    members: ['You', 'Ava', 'Marco', 'Jules', 'Nori', 'Sol'],
    unread: 4,
    status: '6 members',
    accent: '#8b5cf6',
    mood: 'Electric violet',
    page: 'World',
    messages: [
      { id: 'crate-1', sender: 'system', author: 'System', body: 'Ava added Jules to the room.', time: '6:54 PM' },
      { id: 'crate-2', sender: 'other', author: 'Marco', body: 'Keep the first three records humid and slow.', time: '6:58 PM' },
      {
        id: 'crate-3',
        sender: 'other',
        author: 'Jules',
        body: 'I found the transition.',
        time: '7:01 PM',
        track: TRACK_LIBRARY[1],
      },
      { id: 'crate-4', sender: 'you', author: 'You', body: 'Perfect. That is the bridge into the house section.', time: '7:03 PM' },
    ],
    queue: [TRACK_LIBRARY[1], TRACK_LIBRARY[0], TRACK_LIBRARY[2]],
  },
  {
    id: 'marco',
    title: 'Marco',
    subtitle: 'wants one more after-hours pick',
    kind: 'dm',
    members: ['You', 'Marco'],
    unread: 0,
    status: 'seen 1h ago',
    accent: '#06b6d4',
    mood: 'Cyan drift',
    page: 'Library',
    messages: [
      { id: 'marco-1', sender: 'you', author: 'You', body: 'Still thinking about that warehouse set.', time: '5:40 PM' },
      { id: 'marco-2', sender: 'other', author: 'Marco', body: 'Send me one more for the drive home.', time: '5:45 PM' },
    ],
    queue: [TRACK_LIBRARY[2]],
  },
  {
    id: 'afterglow',
    title: 'Afterglow FM',
    subtitle: 'Sunday reconstruction room',
    kind: 'group',
    members: ['You', 'Nori', 'Cass', 'Pia'],
    unread: 1,
    status: '4 members',
    accent: '#10b981',
    mood: 'Green room',
    page: 'World',
    messages: [
      { id: 'after-1', sender: 'other', author: 'Pia', body: 'Sunday set needs more air at the top.', time: '3:11 PM' },
      { id: 'after-2', sender: 'you', author: 'You', body: 'I have one that feels like sunrise through fog.', time: '3:15 PM' },
    ],
    queue: [TRACK_LIBRARY[2], TRACK_LIBRARY[1]],
  },
];

const DESIGN_OPTIONS: Array<{ id: DesignMode; label: string; title: string; note: string }> = [
  {
    id: 'workspace',
    label: 'Option 1',
    title: 'Split Inbox Workspace',
    note: 'Inbox rail, thread, and context panel. Best for a real messaging launch.',
  },
  {
    id: 'canvas',
    label: 'Option 2',
    title: 'Thread-First Social Canvas',
    note: 'The conversation becomes the stage and track shares become the visual hero.',
  },
  {
    id: 'drawer',
    label: 'Option 3',
    title: 'Quick Message Drawer',
    note: 'Low-interruption messaging layered on top of the rest of Juke.',
  },
];

const FILTER_OPTIONS: Array<{ id: FilterMode; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'unread', label: 'Unread' },
  { id: 'groups', label: 'Groups' },
];

const buildReply = (conversation: Conversation): Message => {
  const withTrack = conversation.messages.filter((message) => message.track).length % 2 === 0;
  return {
    id: `${conversation.id}-reply-${Date.now()}`,
    sender: 'other',
    author: conversation.kind === 'group' ? conversation.members[(conversation.messages.length % (conversation.members.length - 1)) + 1] : conversation.title,
    body: conversation.kind === 'group'
      ? 'That change tightened the pacing immediately.'
      : 'That works. Send the next one when you have it.',
    time: 'Just now',
    track: withTrack ? conversation.queue[(conversation.messages.length + 1) % conversation.queue.length] : undefined,
  };
};

const MessageDesignLabRoute = () => {
  const [design, setDesign] = useState<DesignMode>('workspace');
  const [previewMode, setPreviewMode] = useState<PreviewMode>('desktop');
  const [filter, setFilter] = useState<FilterMode>('all');
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState('');
  const [queuedTrack, setQueuedTrack] = useState<TrackAttachment | null>(TRACK_LIBRARY[1]);
  const [conversations, setConversations] = useState<Conversation[]>(INITIAL_CONVERSATIONS);
  const [activeConversationId, setActiveConversationId] = useState<string>(INITIAL_CONVERSATIONS[1].id);

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    return conversations.filter((conversation) => {
      if (filter === 'unread' && conversation.unread === 0) {
        return false;
      }
      if (filter === 'groups' && conversation.kind !== 'group') {
        return false;
      }
      if (!query) {
        return true;
      }
      return `${conversation.title} ${conversation.subtitle} ${conversation.members.join(' ')}`
        .toLowerCase()
        .includes(query);
    });
  }, [conversations, filter, search]);

  const activeConversation = filteredConversations.find((conversation) => conversation.id === activeConversationId)
    ?? conversations.find((conversation) => conversation.id === activeConversationId)
    ?? conversations[0];

  const totalUnread = conversations.reduce((sum, conversation) => sum + conversation.unread, 0);

  const selectConversation = (conversationId: string) => {
    setActiveConversationId(conversationId);
    setConversations((current) => current.map((conversation) => (
      conversation.id === conversationId
        ? { ...conversation, unread: 0 }
        : conversation
    )));
  };

  const handleSend = () => {
    const content = draft.trim();
    if (!content && !queuedTrack) {
      return;
    }
    const nextMessage: Message = {
      id: `${activeConversation.id}-self-${Date.now()}`,
      sender: 'you',
      author: 'You',
      body: content || 'Dropping this in here.',
      time: 'Just now',
      track: queuedTrack ?? undefined,
    };
    setConversations((current) => current.map((conversation) => (
      conversation.id === activeConversation.id
        ? { ...conversation, messages: [...conversation.messages, nextMessage], subtitle: nextMessage.body, unread: 0 }
        : conversation
    )));
    setDraft('');
    setQueuedTrack(null);
  };

  const handleSimulateReply = () => {
    setConversations((current) => current.map((conversation) => {
      if (conversation.id !== activeConversation.id) {
        return conversation;
      }
      const reply = buildReply(conversation);
      return {
        ...conversation,
        messages: [...conversation.messages, reply],
        subtitle: reply.track ? `${reply.author} shared ${reply.track.title}` : reply.body,
        unread: 0,
      };
    }));
  };

  const handleLaunchFrom = (page: string) => {
    const target = conversations.find((conversation) => conversation.page === page) ?? conversations[0];
    setDesign(page === 'Library' ? 'drawer' : page === 'World' ? 'canvas' : 'workspace');
    selectConversation(target.id);
  };

  const handleQuickTrack = (track: TrackAttachment) => {
    setQueuedTrack(track);
  };

  return (
    <section className="message-lab">
      <div className="message-lab__hero card">
        <div className="card__body">
          <div className="message-lab__hero-top">
            <div>
              <p className="eyebrow">Interactive Lab</p>
              <h1>Web messaging concepts you can actually click through</h1>
              <p className="muted">
                These are local-state prototypes, not backend-connected screens. The layouts, flows, and composer behavior are live so
                you can compare how each design feels inside the Juke shell.
              </p>
            </div>
            <div className="message-lab__stats">
              <div>
                <span className="message-lab__stat-value">{filteredConversations.length}</span>
                <span className="message-lab__stat-label">visible threads</span>
              </div>
              <div>
                <span className="message-lab__stat-value">{totalUnread}</span>
                <span className="message-lab__stat-label">unread messages</span>
              </div>
            </div>
          </div>

          <div className="message-lab__controls">
            <div className="message-lab__control-group">
              {DESIGN_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className={`message-lab__segmented${design === option.id ? ' message-lab__segmented--active' : ''}`}
                  onClick={() => setDesign(option.id)}
                >
                  <span>{option.label}</span>
                  <strong>{option.title}</strong>
                </button>
              ))}
            </div>

            <div className="message-lab__utility-row">
              <div className="message-lab__toggle-group">
                <button
                  type="button"
                  className={`message-lab__toggle${previewMode === 'desktop' ? ' message-lab__toggle--active' : ''}`}
                  onClick={() => setPreviewMode('desktop')}
                >
                  Desktop
                </button>
                <button
                  type="button"
                  className={`message-lab__toggle${previewMode === 'mobile' ? ' message-lab__toggle--active' : ''}`}
                  onClick={() => setPreviewMode('mobile')}
                >
                  Mobile
                </button>
              </div>

              <div className="message-lab__launches">
                <span className="eyebrow">Launch from</span>
                {['Profile', 'World', 'Library'].map((page) => (
                  <button key={page} type="button" className="message-lab__chip" onClick={() => handleLaunchFrom(page)}>
                    {page}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="message-lab__note">
            <strong>{DESIGN_OPTIONS.find((option) => option.id === design)?.title}</strong>
            <span>{DESIGN_OPTIONS.find((option) => option.id === design)?.note}</span>
          </div>
        </div>
      </div>

      <div className={`message-lab__frame message-lab__frame--${previewMode}`}>
        <div className={`message-lab__device message-lab__device--${design}`}>
          {design === 'workspace' ? (
            <WorkspaceDesign
              conversations={filteredConversations}
              activeConversation={activeConversation}
              filter={filter}
              search={search}
              draft={draft}
              queuedTrack={queuedTrack}
              onSearchChange={setSearch}
              onFilterChange={setFilter}
              onSelectConversation={selectConversation}
              onDraftChange={setDraft}
              onSend={handleSend}
              onSimulateReply={handleSimulateReply}
              onQueueTrack={handleQuickTrack}
              previewMode={previewMode}
            />
          ) : null}

          {design === 'canvas' ? (
            <CanvasDesign
              conversations={filteredConversations}
              activeConversation={activeConversation}
              draft={draft}
              queuedTrack={queuedTrack}
              onSearchChange={setSearch}
              onSelectConversation={selectConversation}
              onDraftChange={setDraft}
              onSend={handleSend}
              onSimulateReply={handleSimulateReply}
              onQueueTrack={handleQuickTrack}
              search={search}
              previewMode={previewMode}
            />
          ) : null}

          {design === 'drawer' ? (
            <DrawerDesign
              conversations={filteredConversations}
              activeConversation={activeConversation}
              draft={draft}
              queuedTrack={queuedTrack}
              onSelectConversation={selectConversation}
              onDraftChange={setDraft}
              onSend={handleSend}
              onSimulateReply={handleSimulateReply}
              onQueueTrack={handleQuickTrack}
              previewMode={previewMode}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
};

type SharedDesignProps = {
  conversations: Conversation[];
  activeConversation: Conversation;
  draft: string;
  queuedTrack: TrackAttachment | null;
  previewMode: PreviewMode;
  onSelectConversation: (conversationId: string) => void;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onSimulateReply: () => void;
  onQueueTrack: (track: TrackAttachment) => void;
};

type WorkspaceDesignProps = SharedDesignProps & {
  filter: FilterMode;
  search: string;
  onSearchChange: (value: string) => void;
  onFilterChange: (value: FilterMode) => void;
};

const WorkspaceDesign = ({
  conversations,
  activeConversation,
  filter,
  search,
  draft,
  queuedTrack,
  onSearchChange,
  onFilterChange,
  onSelectConversation,
  onDraftChange,
  onSend,
  onSimulateReply,
  onQueueTrack,
  previewMode,
}: WorkspaceDesignProps) => (
  <div className={`message-ui message-ui--workspace${previewMode === 'mobile' ? ' message-ui--stacked' : ''}`}>
    <aside className="message-ui__rail">
      <div className="message-ui__rail-top">
        <p className="eyebrow">Inbox</p>
        <input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          className="message-ui__search"
          placeholder="Search names or rooms"
        />
      </div>
      <div className="message-ui__pill-row">
        {FILTER_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            className={`message-ui__pill${filter === option.id ? ' message-ui__pill--active' : ''}`}
            onClick={() => onFilterChange(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <ConversationList conversations={conversations} activeConversationId={activeConversation.id} onSelectConversation={onSelectConversation} />
    </aside>
    <ThreadPanel
      activeConversation={activeConversation}
      draft={draft}
      queuedTrack={queuedTrack}
      onDraftChange={onDraftChange}
      onSend={onSend}
      onSimulateReply={onSimulateReply}
      onQueueTrack={onQueueTrack}
      emphasizeTrack={false}
    />
    <aside className="message-ui__context">
      <div className="message-ui__context-card">
        <p className="eyebrow">Room mood</p>
        <h3>{activeConversation.mood}</h3>
        <p className="muted">{activeConversation.kind === 'group' ? `${activeConversation.members.length} members` : 'Direct message'}</p>
      </div>
      <div className="message-ui__context-card">
        <p className="eyebrow">Members</p>
        <div className="message-ui__member-list">
          {activeConversation.members.map((member) => (
            <span key={member} className="message-ui__member-chip">{member}</span>
          ))}
        </div>
      </div>
      <div className="message-ui__context-card">
        <p className="eyebrow">Shared tracks</p>
        <div className="message-ui__track-stack">
          {activeConversation.queue.map((track) => (
            <button key={`${activeConversation.id}-${track.title}`} type="button" className="message-ui__mini-track" onClick={() => onQueueTrack(track)}>
              <span className="message-ui__mini-track-swatch" style={{ background: track.color }} />
              <span>
                <strong>{track.title}</strong>
                <small>{track.artist}</small>
              </span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  </div>
);

type CanvasDesignProps = SharedDesignProps & {
  search: string;
  onSearchChange: (value: string) => void;
};

const CanvasDesign = ({
  conversations,
  activeConversation,
  draft,
  queuedTrack,
  onSearchChange,
  onSelectConversation,
  onDraftChange,
  onSend,
  onSimulateReply,
  onQueueTrack,
  search,
  previewMode,
}: CanvasDesignProps) => (
  <div
    className={`message-ui message-ui--canvas${previewMode === 'mobile' ? ' message-ui--stacked' : ''}`}
    style={{ ['--conversation-accent' as string]: activeConversation.accent }}
  >
    <aside className="message-ui__mini-rail">
      <p className="eyebrow">Now listening with</p>
      <input
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        className="message-ui__search"
        placeholder="Filter scenes"
      />
      <ConversationList conversations={conversations} activeConversationId={activeConversation.id} onSelectConversation={onSelectConversation} compact />
    </aside>
    <div className="message-ui__stage">
      <div className="message-ui__stage-header">
        <div>
          <p className="eyebrow">Conversation stage</p>
          <h2>{activeConversation.title}</h2>
          <p className="muted">{activeConversation.subtitle}</p>
        </div>
        <button type="button" className="message-ui__action" onClick={onSimulateReply}>Simulate reply</button>
      </div>
      <div className="message-ui__message-wall">
        {activeConversation.messages.map((message) => (
          <article
            key={message.id}
            className={`message-ui__bubble message-ui__bubble--${message.sender}${message.track ? ' message-ui__bubble--track' : ''}`}
          >
            <header>
              <strong>{message.author}</strong>
              <span>{message.time}</span>
            </header>
            <p>{message.body}</p>
            {message.track ? <TrackCard track={message.track} emphasize /> : null}
          </article>
        ))}
      </div>
      <Composer
        draft={draft}
        queuedTrack={queuedTrack}
        onDraftChange={onDraftChange}
        onSend={onSend}
        onQueueTrack={onQueueTrack}
        emphasizeTrack
      />
    </div>
  </div>
);

const DrawerDesign = ({
  conversations,
  activeConversation,
  draft,
  queuedTrack,
  onSelectConversation,
  onDraftChange,
  onSend,
  onSimulateReply,
  onQueueTrack,
  previewMode,
}: SharedDesignProps) => (
  <div className={`message-ui message-ui--drawer${previewMode === 'mobile' ? ' message-ui--mobile-drawer' : ''}`}>
    <div className="message-ui__underlay">
      <div className="message-ui__underlay-card">
        <p className="eyebrow">Underlying page</p>
        <h2>{activeConversation.page}</h2>
        <p className="muted">This concept keeps the rest of Juke visible while the drawer stays open.</p>
        <div className="message-ui__underlay-actions">
          <button type="button" className="message-ui__chip">Open profile</button>
          <button type="button" className="message-ui__chip">Play current track</button>
          <button type="button" className="message-ui__chip" onClick={onSimulateReply}>Simulate incoming DM</button>
        </div>
      </div>
      <div className="message-ui__underlay-grid">
        {['Recently played', 'World activity', 'Recommended cuts'].map((panel) => (
          <div key={panel} className="message-ui__underlay-panel">
            <p className="eyebrow">{panel}</p>
            <div className="message-ui__skeleton" />
            <div className="message-ui__skeleton" />
            <div className="message-ui__skeleton message-ui__skeleton--short" />
          </div>
        ))}
      </div>
    </div>

    <aside className="message-ui__drawer">
      <div className="message-ui__drawer-header">
        <div>
          <p className="eyebrow">Messages</p>
          <h3>{activeConversation.title}</h3>
        </div>
        <span className="message-ui__drawer-dot" />
      </div>
      <ConversationList conversations={conversations} activeConversationId={activeConversation.id} onSelectConversation={onSelectConversation} compact />
      <div className="message-ui__drawer-thread">
        {activeConversation.messages.map((message) => (
          <article key={message.id} className={`message-ui__bubble message-ui__bubble--${message.sender}`}>
            <header>
              <strong>{message.author}</strong>
              <span>{message.time}</span>
            </header>
            <p>{message.body}</p>
            {message.track ? <TrackCard track={message.track} /> : null}
          </article>
        ))}
      </div>
      <Composer draft={draft} queuedTrack={queuedTrack} onDraftChange={onDraftChange} onSend={onSend} onQueueTrack={onQueueTrack} />
    </aside>
  </div>
);

const ConversationList = ({
  conversations,
  activeConversationId,
  onSelectConversation,
  compact = false,
}: {
  conversations: Conversation[];
  activeConversationId: string;
  onSelectConversation: (conversationId: string) => void;
  compact?: boolean;
}) => (
  <div className={`message-ui__conversation-list${compact ? ' message-ui__conversation-list--compact' : ''}`}>
    {conversations.map((conversation) => (
      <button
        key={conversation.id}
        type="button"
        className={`message-ui__conversation${activeConversationId === conversation.id ? ' message-ui__conversation--active' : ''}`}
        onClick={() => onSelectConversation(conversation.id)}
      >
        <span className="message-ui__avatar" style={{ background: conversation.accent }}>
          {conversation.title.charAt(0)}
        </span>
        <span className="message-ui__conversation-copy">
          <strong>{conversation.title}</strong>
          <small>{conversation.subtitle}</small>
        </span>
        {conversation.unread > 0 ? <span className="message-ui__badge">{conversation.unread}</span> : null}
      </button>
    ))}
  </div>
);

const ThreadPanel = ({
  activeConversation,
  draft,
  queuedTrack,
  onDraftChange,
  onSend,
  onSimulateReply,
  onQueueTrack,
  emphasizeTrack,
}: {
  activeConversation: Conversation;
  draft: string;
  queuedTrack: TrackAttachment | null;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onSimulateReply: () => void;
  onQueueTrack: (track: TrackAttachment) => void;
  emphasizeTrack: boolean;
}) => (
  <section className="message-ui__thread">
    <div className="message-ui__thread-header">
      <div>
        <p className="eyebrow">{activeConversation.kind === 'group' ? 'Group thread' : 'Direct message'}</p>
        <h2>{activeConversation.title}</h2>
        <p className="muted">{activeConversation.status}</p>
      </div>
      <button type="button" className="message-ui__action" onClick={onSimulateReply}>
        Simulate reply
      </button>
    </div>
    <div className="message-ui__thread-body">
      {activeConversation.messages.map((message) => (
        <article
          key={message.id}
          className={`message-ui__bubble message-ui__bubble--${message.sender}${message.track ? ' message-ui__bubble--track' : ''}`}
        >
          <header>
            <strong>{message.author}</strong>
            <span>{message.time}</span>
          </header>
          <p>{message.body}</p>
          {message.track ? <TrackCard track={message.track} emphasize={emphasizeTrack} /> : null}
        </article>
      ))}
    </div>
    <Composer
      draft={draft}
      queuedTrack={queuedTrack}
      onDraftChange={onDraftChange}
      onSend={onSend}
      onQueueTrack={onQueueTrack}
      emphasizeTrack={emphasizeTrack}
    />
  </section>
);

const Composer = ({
  draft,
  queuedTrack,
  onDraftChange,
  onSend,
  onQueueTrack,
  emphasizeTrack = false,
}: {
  draft: string;
  queuedTrack: TrackAttachment | null;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onQueueTrack: (track: TrackAttachment) => void;
  emphasizeTrack?: boolean;
}) => (
  <div className="message-ui__composer">
    {queuedTrack ? (
      <div className={`message-ui__queued${emphasizeTrack ? ' message-ui__queued--hero' : ''}`}>
        <span className="message-ui__queued-swatch" style={{ background: queuedTrack.color }} />
        <div>
          <strong>{queuedTrack.title}</strong>
          <small>{queuedTrack.artist} • {queuedTrack.album}</small>
        </div>
      </div>
    ) : null}
    <textarea
      value={draft}
      onChange={(event) => onDraftChange(event.target.value)}
      className="message-ui__composer-input"
      placeholder="Type a message, react to the track, or line up the next transition..."
      rows={3}
    />
    <div className="message-ui__composer-actions">
      <div className="message-ui__track-picker">
        {TRACK_LIBRARY.map((track) => (
          <button key={track.title} type="button" className="message-ui__track-chip" onClick={() => onQueueTrack(track)}>
            {track.title}
          </button>
        ))}
      </div>
      <button type="button" className="message-ui__send" onClick={onSend}>
        Send
      </button>
    </div>
  </div>
);

const TrackCard = ({ track, emphasize = false }: { track: TrackAttachment; emphasize?: boolean }) => (
  <div className={`message-ui__track-card${emphasize ? ' message-ui__track-card--hero' : ''}`}>
    <div className="message-ui__track-art" style={{ background: `linear-gradient(135deg, ${track.color}, rgba(15, 23, 42, 0.9))` }} />
    <div>
      <strong>{track.title}</strong>
      <p>{track.artist}</p>
      <small>{track.album}</small>
    </div>
  </div>
);

export default MessageDesignLabRoute;

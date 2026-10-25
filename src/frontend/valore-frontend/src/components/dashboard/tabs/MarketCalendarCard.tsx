import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  UnstyledButton,
} from '@mantine/core';
import { IconBuildingBank, IconCalendarEvent, IconChartLine, IconFlame, IconReportMoney } from '@tabler/icons-react';
import { formatNum } from '../formatters';
import { DEFAULT_MARKET_CALENDAR_DAYS, useMarketCalendar } from '../hooks/queries';
import type { MarketCalendarCategory, MarketCalendarEvent, MarketCalendarResponse } from '../../../services/api';

const CALENDAR_TZ = 'Europe/Rome';
// Events per day shown before "Mostra altri": high-impact ones are always shown.
const VISIBLE_EVENTS_PER_DAY = 6;
const MAX_HIGHLIGHTS = 6;

const CATEGORY_STYLE: Record<MarketCalendarCategory, { color: string; label: string; icon: typeof IconBuildingBank }> = {
  central_bank: { color: 'violet', label: 'Banca centrale', icon: IconBuildingBank },
  earnings: { color: 'blue', label: 'Trimestrale', icon: IconReportMoney },
  macro: { color: 'teal', label: 'Dato macro', icon: IconChartLine },
};

const REGION_LABELS: Record<string, string> = {
  US: 'USA',
  EU: 'Eurozona',
  DE: 'Germania',
  IT: 'Italia',
};

const timeFormatter = new Intl.DateTimeFormat('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: CALENDAR_TZ });
const dayFormatter = new Intl.DateTimeFormat('it-IT', { weekday: 'long', day: 'numeric', month: 'long', timeZone: CALENDAR_TZ });
const shortDayFormatter = new Intl.DateTimeFormat('it-IT', { weekday: 'short', day: 'numeric', month: 'short', timeZone: CALENDAR_TZ });
const isoDayFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: CALENDAR_TZ });

// Noon UTC keeps the calendar day unchanged in Europe/Rome.
const parseDay = (day: string) => new Date(`${day}T12:00:00Z`);

const formatDayLabel = (day: string) => {
  const label = dayFormatter.format(parseDay(day));
  return label.charAt(0).toUpperCase() + label.slice(1);
};

const formatValue = (value: number) =>
  new Intl.NumberFormat('it-IT', { useGrouping: 'always', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(value);

function formatEventTime(event: MarketCalendarEvent): string {
  if (event.time_hint) return event.time_hint;
  if (event.starts_at) return `ore ${timeFormatter.format(new Date(event.starts_at))}`;
  return 'Orario da confermare';
}

function eventDetails(event: MarketCalendarEvent): string | null {
  const parts: string[] = [];
  if (event.category === 'earnings') {
    if (event.market_cap != null) parts.push(`Cap. ${formatNum(event.market_cap / 1e9, 0)} mld $`);
    if (event.eps_actual != null) parts.push(`EPS ${formatValue(event.eps_actual)}`);
    if (event.eps_estimate != null) parts.push(`EPS atteso ${formatValue(event.eps_estimate)}`);
  } else if (event.category === 'macro') {
    if (event.source_name) parts.push(event.period ? `${event.source_name} (${event.period})` : event.source_name);
    if (event.actual != null) parts.push(`Effettivo ${formatValue(event.actual)}`);
    if (event.expected != null) parts.push(`Atteso ${formatValue(event.expected)}`);
    if (event.previous != null) parts.push(`Prec. ${formatValue(event.previous)}`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

function EventRow({
  event,
  showDescription,
  onSymbolClick,
}: {
  event: MarketCalendarEvent;
  showDescription: boolean;
  onSymbolClick?: (symbol: string) => void;
}) {
  const style = CATEGORY_STYLE[event.category];
  const Icon = style.icon;
  const details = eventDetails(event);
  const region = event.region ? REGION_LABELS[event.region] ?? event.region : null;
  const clickable = event.symbol != null && onSymbolClick != null;

  const title = (
    <Text size="sm" fw={600} style={clickable ? { textDecoration: 'underline dotted' } : undefined}>
      {event.title}
    </Text>
  );

  return (
    <Group gap="xs" wrap="nowrap" align="flex-start">
      <ThemeIcon size="sm" radius="xl" variant="light" color={style.color} aria-label={style.label} mt={2}>
        <Icon size={13} />
      </ThemeIcon>
      <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
        <Group gap={6} wrap="wrap">
          {clickable ? (
            <UnstyledButton onClick={() => onSymbolClick(event.symbol!)} aria-label={`Dettagli ${event.symbol}`}>
              {title}
            </UnstyledButton>
          ) : (
            title
          )}
          {event.importance === 'high' && (
            <Badge size="xs" variant="light" color="red">
              Alto impatto
            </Badge>
          )}
          {event.tags.map((tag) => (
            <Badge key={tag} size="xs" variant="outline" color="gray">
              {tag}
            </Badge>
          ))}
        </Group>
        <Text size="xs" c="dimmed">
          {[formatEventTime(event), region, event.symbol].filter(Boolean).join(' · ')}
        </Text>
        {details && (
          <Text size="xs" c="dimmed">
            {details}
          </Text>
        )}
        {showDescription && event.description && <Text size="xs">{event.description}</Text>}
      </Stack>
    </Group>
  );
}

function DayColumn({
  day,
  events,
  isToday,
  onSymbolClick,
}: {
  day: string;
  events: MarketCalendarEvent[];
  isToday: boolean;
  onSymbolClick?: (symbol: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  // Events come sorted by importance, so the hidden ones are always medium impact.
  const visibleCount = Math.max(VISIBLE_EVENTS_PER_DAY, events.filter((e) => e.importance === 'high').length);
  const visible = expanded ? events : events.slice(0, visibleCount);
  const hiddenCount = events.length - visible.length;

  return (
    <Paper withBorder radius="sm" p="sm">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Text fw={700} size="sm">
          {formatDayLabel(day)}
        </Text>
        {isToday && (
          <Badge size="xs" variant="filled">
            Oggi
          </Badge>
        )}
      </Group>
      {events.length === 0 ? (
        <Text size="xs" c="dimmed">
          Nessun evento di rilievo in calendario.
        </Text>
      ) : (
        <Stack gap="sm">
          {visible.map((event, index) => (
            <EventRow
              key={event.id}
              event={event}
              // Shared descriptions (e.g. the Big Tech one) are shown once per day.
              showDescription={visible.findIndex((other) => other.description === event.description) === index}
              onSymbolClick={onSymbolClick}
            />
          ))}
          {events.length > visibleCount && (
            <Button variant="subtle" size="compact-xs" onClick={() => setExpanded((v) => !v)}>
              {expanded ? 'Mostra meno' : `Mostra altri ${hiddenCount}`}
            </Button>
          )}
        </Stack>
      )}
    </Paper>
  );
}

function Highlights({ data }: { data: MarketCalendarResponse }) {
  const highlights = data.days.flatMap((d) => d.events.filter((e) => e.importance === 'high'));
  if (highlights.length === 0) return null;
  const shown = highlights.slice(0, MAX_HIGHLIGHTS);

  return (
    <Paper radius="sm" p="sm" bg="var(--mantine-color-default-hover)">
      <Group gap={6} mb={6}>
        <IconFlame size={16} color="var(--mantine-color-orange-6)" />
        <Text fw={600} size="sm">
          Da tenere d&apos;occhio
        </Text>
      </Group>
      <Stack gap={4}>
        {shown.map((event) => (
          <Text key={event.id} size="sm">
            <Text span fw={600}>
              {shortDayFormatter.format(parseDay(event.day))}
              {event.starts_at && !event.time_hint ? `, ${timeFormatter.format(new Date(event.starts_at))}` : ''}
            </Text>{' '}
            — {event.title}
          </Text>
        ))}
        {highlights.length > shown.length && (
          <Text size="xs" c="dimmed">
            e altri {highlights.length - shown.length} eventi ad alto impatto
          </Text>
        )}
      </Stack>
    </Paper>
  );
}

export function MarketCalendarView({
  data,
  today,
  onSymbolClick,
}: {
  data: MarketCalendarResponse;
  today: string;
  onSymbolClick?: (symbol: string) => void;
}) {
  return (
    <Stack gap="sm">
      {data.warnings.length > 0 && (
        <Alert color="yellow" variant="light" p="xs">
          {data.warnings.map((warning) => (
            <Text key={warning} size="xs">
              {warning}
            </Text>
          ))}
        </Alert>
      )}
      <Highlights data={data} />
      <SimpleGrid cols={{ base: 1, sm: Math.min(data.days.length, 3), lg: data.days.length }} spacing="sm">
        {data.days.map((d) => (
          <DayColumn key={d.day} day={d.day} events={d.events} isToday={d.day === today} onSymbolClick={onSymbolClick} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}

export function MarketCalendarCard({ onSymbolClick }: { onSymbolClick?: (symbol: string) => void }) {
  const [days, setDays] = useState(String(DEFAULT_MARKET_CALENDAR_DAYS));
  const { data, isLoading, error } = useMarketCalendar(Number(days));

  return (
    <Card withBorder radius="md" p="sm" shadow="sm">
      <Group justify="space-between" align="flex-start" mb="sm" gap="xs">
        <Group gap="xs" wrap="nowrap" align="flex-start">
          <ThemeIcon variant="light" radius="md" aria-hidden>
            <IconCalendarEvent size={18} />
          </ThemeIcon>
          <div>
            <Text fw={700}>Prossimi giorni sui mercati</Text>
            <Text size="xs" c="dimmed">
              Banche centrali, trimestrali delle big cap e dati macro · orari italiani
            </Text>
          </div>
        </Group>
        <SegmentedControl
          size="xs"
          value={days}
          onChange={setDays}
          data={[
            { label: '3 giorni', value: '3' },
            { label: '5 giorni', value: '5' },
          ]}
        />
      </Group>

      {isLoading && !data && (
        <Group gap="xs">
          <Loader size="xs" />
          <Text size="sm" c="dimmed">
            Caricamento calendario...
          </Text>
        </Group>
      )}
      {error && !data && (
        <Alert color="red" variant="light">
          {error instanceof Error ? error.message : 'Errore caricamento calendario'}
        </Alert>
      )}
      {data && <MarketCalendarView data={data} today={isoDayFormatter.format(new Date())} onSymbolClick={onSymbolClick} />}
    </Card>
  );
}

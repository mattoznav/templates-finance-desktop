import { session } from './session.svelte.ts';

const LOCALE = 'en-GB';
const moneyFormats = new Map<string, Intl.NumberFormat>();

function moneyFormat(currency: string, compact: boolean): Intl.NumberFormat {
	const key = `${currency}-${compact}`;
	let format = moneyFormats.get(key);
	if (!format) {
		format = new Intl.NumberFormat(LOCALE, {
			style: 'currency',
			currency,
			...(compact
				? { notation: 'compact', maximumFractionDigits: 1 }
				: { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		});
		moneyFormats.set(key, format);
	}
	return format;
}

export function money(cents: number | null | undefined, options: { sign?: boolean; compact?: boolean } = {}): string {
	if (cents === null || cents === undefined) return '—';
	const text = moneyFormat(session.currency, !!options.compact).format(cents / 100);
	return options.sign && cents > 0 ? `+${text}` : text;
}

export function currencySymbol(): string {
	return (
		moneyFormat(session.currency, false)
			.formatToParts(0)
			.find((p) => p.type === 'currency')?.value ?? session.currency
	);
}

export function pct(value: number | null | undefined, options: { sign?: boolean; digits?: number } = {}): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—';
	const text = new Intl.NumberFormat(LOCALE, {
		style: 'percent',
		minimumFractionDigits: options.digits ?? 1,
		maximumFractionDigits: options.digits ?? 1
	}).format(value);
	return options.sign && value > 0 ? `+${text}` : text;
}

export function quantity(value: number): string {
	return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 6 }).format(value);
}

export function price(value: number | null): string {
	if (value === null) return '—';
	return new Intl.NumberFormat(LOCALE, {
		style: 'currency',
		currency: session.currency,
		minimumFractionDigits: 2,
		maximumFractionDigits: value < 10 ? 4 : 2
	}).format(value);
}

export function shortDate(iso: string): string {
	return new Date(`${iso}T12:00:00`).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function dayMonth(iso: string): string {
	return new Date(`${iso}T12:00:00`).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' });
}

export function monthLabel(month: string, style: 'long' | 'short' = 'long'): string {
	return new Date(`${month}-15T12:00:00`).toLocaleDateString(LOCALE, { month: style, year: 'numeric' });
}

/** 'Oct 26', for chart axes. */
export function axisMonth(iso: string): string {
	return new Date(`${iso.slice(0, 7)}-15T12:00:00`).toLocaleDateString(LOCALE, { month: 'short', year: '2-digit' });
}

export function today(): string {
	const now = new Date();
	return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function shiftMonth(month: string, delta: number): string {
	const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + delta;
	return `${String(Math.floor(index / 12)).padStart(4, '0')}-${String((index % 12) + 1).padStart(2, '0')}`;
}

/** Reads what people type: '12', '12.5', '1.234,56', '-40'. Returns cents or null. */
export function parseMoney(text: string): number | null {
	let raw = text.trim().replace(/[^\d.,-]/g, '');
	if (!raw || !/\d/.test(raw)) return null;
	const negative = raw.startsWith('-');
	raw = raw.replace(/-/g, '');
	const lastComma = raw.lastIndexOf(',');
	const lastDot = raw.lastIndexOf('.');
	if (lastComma > lastDot) {
		raw = /,\d{1,2}$/.test(raw) ? raw.replace(/\./g, '').replace(',', '.') : raw.replace(/,/g, '');
	} else {
		raw = raw.replace(/,/g, '');
	}
	if ((raw.match(/\./g) ?? []).length > 1) return null;
	const value = Math.round(Number(raw) * 100);
	if (!Number.isFinite(value)) return null;
	return negative ? -value : value;
}

/** Cents to the plain text shown in an input. */
export function moneyInput(cents: number | null | undefined): string {
	if (cents === null || cents === undefined) return '';
	return (cents / 100).toFixed(2);
}

export const ACCOUNT_KINDS: Record<string, string> = {
	checking: 'Current account',
	savings: 'Savings',
	cash: 'Cash',
	credit_card: 'Credit card',
	brokerage: 'Brokerage',
	other: 'Other'
};

export const ASSET_KINDS: Record<string, string> = {
	etf: 'ETF',
	stock: 'Stock',
	bond: 'Bonds',
	fund: 'Fund',
	crypto: 'Crypto',
	other: 'Other'
};

export const REGIONS: Record<string, string> = {
	global: 'Global',
	north_america: 'North America',
	europe: 'Europe',
	asia_pacific: 'Asia Pacific',
	emerging: 'Emerging markets',
	other: 'Other'
};

export const CHART_COLORS = ['#d9a84e', '#63c393', '#6fa8dc', '#c58fd8', '#ef8a78', '#4fb3b3', '#e3c26b', '#8a94a6'];

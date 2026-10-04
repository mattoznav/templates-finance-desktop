// Shapes returned by the Python core. Money is always integer cents.

export interface Status {
	vault_exists: boolean;
	unlocked: boolean;
	demo: boolean;
	seconds_left?: number;
	auto_lock_minutes?: number;
	currency?: string;
	saved_at?: string | null;
}

export interface Settings {
	currency: string;
	auto_lock_minutes: number;
	offline_mode: boolean;
	created_at: string;
}

export type AccountKind = 'checking' | 'savings' | 'cash' | 'credit_card' | 'brokerage' | 'other';

export interface Account {
	id: number;
	name: string;
	kind: AccountKind;
	institution: string;
	opening_balance: number;
	opening_date: string;
	archived: boolean;
	balance: number;
	movements: number;
}

export interface Category {
	id: number;
	name: string;
	kind: 'income' | 'expense';
	color: string;
	monthly_budget: number | null;
	usage: number;
}

export interface Rule {
	id: number;
	pattern: string;
	category_id: number;
	category_name: string;
	category_color: string;
}

export interface Transaction {
	id: number;
	account_id: number;
	account_name: string;
	date: string;
	amount: number;
	payee: string;
	category_id: number | null;
	category_name: string | null;
	category_color: string | null;
	note: string;
	transfer_group: string | null;
	counter_account_id: number | null;
	counter_account_name: string | null;
}

export interface TransactionPage {
	items: Transaction[];
	total: number;
	income: number;
	expenses: number;
}

export type AssetKind = 'etf' | 'stock' | 'bond' | 'fund' | 'crypto' | 'other';
export type Region = 'global' | 'north_america' | 'europe' | 'asia_pacific' | 'emerging' | 'other';

export interface Asset {
	id: number;
	symbol: string;
	name: string;
	kind: AssetKind;
	region: Region;
	price_source: 'manual' | 'yahoo' | 'coingecko';
	source_id: string;
	last_price: number | null;
	last_price_date: string | null;
	trades: number;
}

export interface Trade {
	id: number;
	account_id: number;
	account_name: string;
	asset_id: number;
	symbol: string;
	asset_name: string;
	date: string;
	side: 'buy' | 'sell';
	quantity: number;
	price: number;
	fees: number;
	note: string;
}

export interface Dividend {
	id: number;
	account_id: number;
	account_name: string;
	asset_id: number;
	symbol: string;
	asset_name: string;
	date: string;
	amount: number;
	tax: number;
	note: string;
}

export interface Holding {
	asset_id: number;
	symbol: string;
	name: string;
	kind: AssetKind;
	region: Region;
	quantity: number;
	average_cost: number;
	price: number | null;
	price_date: string | null;
	value: number;
	cost: number;
	unrealized: number;
	unrealized_pct: number;
	realized: number;
	dividends: number;
	weight: number;
	open: boolean;
}

export interface AllocationGroup {
	key: string;
	value: number;
	weight: number;
}

export interface Portfolio {
	holdings: Holding[];
	allocation: { kind: AllocationGroup[]; region: AllocationGroup[] };
	totals: {
		value: number;
		cost: number;
		unrealized: number;
		unrealized_pct: number;
		realized: number;
		dividends: number;
		total_return: number;
	};
	stale_prices: string[];
}

export interface SeriesPoint {
	date: string;
	cash: number;
	investments: number;
	cost_basis: number;
	net_worth: number;
}

export interface SpendingSlice {
	id: number | null;
	name: string;
	color: string;
	spent: number;
}

export interface BudgetLine {
	category_id: number;
	name: string;
	color: string;
	budget: number | null;
	spent: number;
	remaining: number | null;
	used: number | null;
	average_3m: number;
}

export interface BudgetReport {
	month: string;
	lines: BudgetLine[];
	uncategorized: number;
	totals: {
		budget: number;
		spent_in_budgets: number;
		income: number;
		expenses: number;
		saved: number;
		savings_rate: number | null;
	};
	progress: number;
}

export interface Overview {
	month: string;
	net_worth: number;
	cash: number;
	investments: number;
	change_this_month: number | null;
	income: number;
	expenses: number;
	savings_rate: number | null;
	series: SeriesPoint[];
	spending: SpendingSlice[];
	budgets: BudgetLine[];
	recent: Transaction[];
	accounts: Account[];
	progress: number;
}

export interface CashFlowMonth {
	month: string;
	income: number;
	expenses: number;
	net: number;
}

export interface DividendSummary {
	by_year: { year: string; gross: number; tax: number; net: number }[];
	trailing_12m: number;
	items: Dividend[];
}

export interface ImportMapping {
	delimiter: string;
	has_header: boolean;
	date_column: number | null;
	date_format: string | null;
	amount_mode: 'single' | 'split';
	amount_column: number | null;
	debit_column: number | null;
	credit_column: number | null;
	payee_column: number | null;
	decimal: 'auto' | 'comma' | 'dot';
	invert: boolean;
}

export interface ImportInspection {
	headers: string[];
	sample: string[][];
	rows: number;
	mapping: ImportMapping;
	date_formats: string[];
}

export interface ImportPreviewRow {
	line: number;
	date: string | null;
	amount: number | null;
	payee: string;
	error: string | null;
	status: 'new' | 'duplicate' | 'error';
	category?: string | null;
}

export interface ImportPreview {
	rows: ImportPreviewRow[];
	new: number;
	duplicate: number;
	error: number;
}

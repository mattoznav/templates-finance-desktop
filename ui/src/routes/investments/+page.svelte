<script lang="ts">
	import { rpc } from '#lib/api.ts';
	import Chart, { tooltipBase, type ThemeColors } from '#lib/components/Chart.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import AssetForm from '#lib/components/forms/AssetForm.svelte';
	import DividendForm from '#lib/components/forms/DividendForm.svelte';
	import TradeForm from '#lib/components/forms/TradeForm.svelte';
	import { ASSET_KINDS, axisMonth, CHART_COLORS, money, monthLabel, pct, price, quantity, REGIONS, shortDate } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account, Asset, Dividend, DividendSummary, Portfolio, SeriesPoint, Settings, Trade } from '#lib/types.ts';

	type Tab = 'holdings' | 'trades' | 'dividends' | 'assets';

	let tab = $state<Tab>('holdings');
	let split = $state<'kind' | 'region'>('kind');
	let portfolio = $state<Portfolio | null>(null);
	let series = $state<SeriesPoint[]>([]);
	let trades = $state<Trade[]>([]);
	let dividends = $state<DividendSummary | null>(null);
	let assets = $state<Asset[]>([]);
	let accounts = $state<Account[]>([]);
	let settings = $state<Settings | null>(null);
	let refreshing = $state(false);

	let editTrade = $state<Trade | null | undefined>(undefined);
	let editDividend = $state<Dividend | null | undefined>(undefined);
	let editAsset = $state<Asset | null | undefined>(undefined);

	$effect(() => {
		void session.version;
		Promise.all([
			rpc<Portfolio>('portfolio'),
			rpc<SeriesPoint[]>('net_worth_series', { months: 36 }),
			rpc<Trade[]>('list_trades'),
			rpc<DividendSummary>('dividends_summary'),
			rpc<Asset[]>('list_assets'),
			rpc<Account[]>('list_accounts'),
			rpc<Settings>('get_settings')
		])
			.then(([p, s, t, d, a, ac, st]) => {
				portfolio = p;
				series = s.filter((x) => x.investments > 0 || x.cost_basis > 0);
				trades = t;
				dividends = d;
				assets = a;
				accounts = ac;
				settings = st;
			})
			.catch((e) => toasts.error(e));
	});

	let open = $derived(portfolio?.holdings.filter((h) => h.open) ?? []);
	let closed = $derived(portfolio?.holdings.filter((h) => !h.open) ?? []);
	let canRefresh = $derived(!settings?.offline_mode && assets.some((a) => a.price_source !== 'manual'));

	async function refresh() {
		refreshing = true;
		try {
			const results = await rpc<{ symbol: string; ok: boolean; message?: string }[]>('refresh_prices');
			const failed = results.filter((r) => !r.ok);
			toasts.show(
				failed.length ? `Updated ${results.length - failed.length}, failed: ${failed.map((f) => `${f.symbol} (${f.message})`).join(', ')}` : `Updated ${results.length} prices`,
				failed.length ? 'error' : 'info'
			);
			session.changed();
		} catch (err) {
			toasts.error(err);
		} finally {
			refreshing = false;
		}
	}

	function performance(c: ThemeColors) {
		return {
			grid: { left: 8, right: 8, top: 28, bottom: 4, containLabel: true },
			legend: { top: 0, right: 0, itemWidth: 14, itemHeight: 3, textStyle: { color: c.muted, fontSize: 12 } },
			tooltip: {
				...tooltipBase(),
				trigger: 'axis',
				formatter: (items: { dataIndex: number }[]) => {
					const p = series[items[0].dataIndex];
					const gain = p.investments - p.cost_basis;
					return `<b>${monthLabel(p.date.slice(0, 7))}</b><br/>Value ${money(p.investments)}<br/>Invested ${money(p.cost_basis)}<br/>Gain <b>${money(gain, { sign: true })}</b>`;
				}
			},
			xAxis: {
				type: 'category',
				data: series.map((p) => p.date),
				axisTick: { show: false },
				axisLine: { lineStyle: { color: c.line } },
				axisLabel: { color: c.faint, fontSize: 11, formatter: axisMonth }
			},
			yAxis: {
				type: 'value',
				splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
				axisLabel: { color: c.faint, fontSize: 11, formatter: (v: number) => money(v, { compact: true }) }
			},
			series: [
				{ name: 'Market value', type: 'line', symbol: 'none', smooth: 0.2, lineStyle: { width: 2, color: c.accent }, areaStyle: { color: c.accent, opacity: 0.12 }, data: series.map((p) => p.investments) },
				{ name: 'Invested', type: 'line', symbol: 'none', step: 'end', lineStyle: { width: 1.5, color: c.muted, type: 'dashed' }, data: series.map((p) => p.cost_basis) }
			]
		};
	}

	function allocation(c: ThemeColors) {
		const groups = portfolio?.allocation[split] ?? [];
		const labels = split === 'kind' ? ASSET_KINDS : REGIONS;
		return {
			tooltip: { ...tooltipBase(), formatter: (p: { name: string; value: number; percent: number }) => `${p.name}<br/><b>${money(p.value)}</b> · ${p.percent}%` },
			series: [
				{
					type: 'pie',
					radius: ['58%', '86%'],
					padAngle: 2,
					itemStyle: { borderRadius: 4 },
					label: { show: false },
					data: groups.map((g, i) => ({ name: labels[g.key] ?? g.key, value: g.value, itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] } }))
				}
			]
		};
	}
</script>

<div class="page">
	<header class="page-head">
		<div>
			<h1>Investments</h1>
			<p>Holdings at their latest price, average cost method.</p>
		</div>
		<div class="actions">
			<button
				class="btn"
				onclick={refresh}
				disabled={!canRefresh || refreshing}
				title={settings?.offline_mode ? 'Offline mode is on (Settings)' : 'Fetch latest prices for assets with an online source'}
			>
				<Icon name="refresh" size={16} />{refreshing ? 'Updating…' : 'Update prices'}
			</button>
			<button class="btn" onclick={() => (editDividend = null)}>Dividend</button>
			<button class="btn primary" onclick={() => (editTrade = null)}><Icon name="plus" size={16} /> Trade</button>
		</div>
	</header>

	{#if portfolio}
		{@const t = portfolio.totals}
		<section class="stats">
			<div class="card main">
				<h3>Market value</h3>
				<div class="display big num">{money(t.value)}</div>
				<p class="muted num">invested {money(t.cost)}</p>
			</div>
			<div class="card">
				<h3>Unrealized</h3>
				<div class="display num" class:pos={t.unrealized > 0} class:neg={t.unrealized < 0}>{money(t.unrealized, { sign: true })}</div>
				<p class="num" class:pos={t.unrealized > 0} class:neg={t.unrealized < 0}>{pct(t.unrealized_pct, { sign: true })}</p>
			</div>
			<div class="card">
				<h3>Realized</h3>
				<div class="display num" class:pos={t.realized > 0} class:neg={t.realized < 0}>{money(t.realized, { sign: true })}</div>
				<p class="muted">from sales</p>
			</div>
			<div class="card">
				<h3>Dividends</h3>
				<div class="display num">{money(t.dividends)}</div>
				<p class="muted num">{money(dividends?.trailing_12m ?? 0)} last 12 months</p>
			</div>
			<div class="card">
				<h3>Total return</h3>
				<div class="display num" class:pos={t.total_return > 0} class:neg={t.total_return < 0}>{money(t.total_return, { sign: true })}</div>
				<p class="muted">gains + dividends</p>
			</div>
		</section>

		{#if portfolio.stale_prices.length}
			<p class="notice warn stale">Prices older than a week: {portfolio.stale_prices.join(', ')}. Update them, or type today's price in the asset.</p>
		{/if}

		{#if open.length}
			<section class="charts">
				<div class="card">
					<div class="card-head"><h2>Value and money invested</h2></div>
					{#if series.length > 1}<Chart height={250} option={performance} />{/if}
				</div>
				<div class="card">
					<div class="card-head">
						<h2>Allocation</h2>
						<div class="tabs">
							<button class:active={split === 'kind'} onclick={() => (split = 'kind')}>Type</button>
							<button class:active={split === 'region'} onclick={() => (split = 'region')}>Region</button>
						</div>
					</div>
					<div class="alloc">
						{#key split}<Chart height={180} option={allocation} />{/key}
						<ul>
							{#each portfolio.allocation[split] as g, i (g.key)}
								<li>
									<i class="dot" style:background={CHART_COLORS[i % CHART_COLORS.length]}></i>
									<span>{(split === 'kind' ? ASSET_KINDS : REGIONS)[g.key] ?? g.key}</span>
									<span class="num muted">{pct(g.weight)}</span>
								</li>
							{/each}
						</ul>
					</div>
				</div>
			</section>
		{/if}

		<div class="tabs main-tabs">
			{#each [['holdings', 'Holdings'], ['trades', 'Trades'], ['dividends', 'Dividends'], ['assets', 'Assets']] as [key, label] (key)}
				<button class:active={tab === key} onclick={() => (tab = key as Tab)}>{label}</button>
			{/each}
		</div>

		<section class="card flush">
			{#if tab === 'holdings'}
				{#if portfolio.holdings.length}
					<table class="table">
						<thead>
							<tr>
								<th>Asset</th><th class="right">Units</th><th class="right">Avg cost</th><th class="right">Price</th>
								<th class="right">Value</th><th class="right">Weight</th><th class="right">Unrealized</th><th class="right">Realized</th><th class="right">Dividends</th>
							</tr>
						</thead>
						<tbody>
							{#each [...open, ...closed] as h (h.asset_id)}
								<tr class="clickable" class:closed={!h.open} onclick={() => (editAsset = assets.find((a) => a.id === h.asset_id) ?? null)}>
									<td>
										<div class="sym">{h.symbol}</div>
										<div class="faint small">{h.name}</div>
									</td>
									<td class="right num">{h.open ? quantity(h.quantity) : 'sold'}</td>
									<td class="right num muted">{h.open ? price(h.average_cost) : ''}</td>
									<td class="right num">
										{price(h.price)}
										{#if h.price_date}<div class="faint small">{shortDate(h.price_date)}</div>{/if}
									</td>
									<td class="right num">{h.open ? money(h.value) : ''}</td>
									<td class="right num muted">{h.open ? pct(h.weight) : ''}</td>
									<td class="right num" class:pos={h.unrealized > 0} class:neg={h.unrealized < 0}>
										{#if h.open}{money(h.unrealized, { sign: true })}<div class="small">{pct(h.unrealized_pct, { sign: true })}</div>{/if}
									</td>
									<td class="right num" class:pos={h.realized > 0} class:neg={h.realized < 0}>{h.realized ? money(h.realized, { sign: true }) : ''}</td>
									<td class="right num">{h.dividends ? money(h.dividends) : ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="empty"><strong>No holdings yet</strong>Add an asset, then record your first trade, or import your broker's trades from the Import page.</div>
				{/if}
			{:else if tab === 'trades'}
				{#if trades.length}
					<table class="table">
						<thead><tr><th>Date</th><th>Asset</th><th></th><th class="right">Units</th><th class="right">Price</th><th class="right">Fees</th><th class="right">Total</th><th>Account</th></tr></thead>
						<tbody>
							{#each trades as t (t.id)}
								{@const gross = Math.round(t.quantity * t.price * 100)}
								<tr class="clickable" onclick={() => (editTrade = t)}>
									<td class="muted num">{shortDate(t.date)}</td>
									<td><span class="sym">{t.symbol}</span> <span class="faint">{t.asset_name}</span></td>
									<td><span class="pill" class:sell={t.side === 'sell'}>{t.side}</span></td>
									<td class="right num">{quantity(t.quantity)}</td>
									<td class="right num">{price(t.price)}</td>
									<td class="right num muted">{t.fees ? money(t.fees) : ''}</td>
									<td class="right num">{money(t.side === 'buy' ? -(gross + t.fees) : gross - t.fees, { sign: true })}</td>
									<td class="muted">{t.account_name}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="empty"><strong>No trades yet</strong></div>
				{/if}
			{:else if tab === 'dividends'}
				{#if dividends?.items.length}
					<div class="years">
						{#each dividends.by_year as y (y.year)}
							<div><h3>{y.year}</h3><span class="display num">{money(y.net)}</span><small class="faint num">gross {money(y.gross)}, tax {money(y.tax)}</small></div>
						{/each}
					</div>
					<table class="table">
						<thead><tr><th>Paid</th><th>Asset</th><th class="right">Gross</th><th class="right">Tax</th><th class="right">Net</th><th>Account</th></tr></thead>
						<tbody>
							{#each dividends.items as d (d.id)}
								<tr class="clickable" onclick={() => (editDividend = d)}>
									<td class="muted num">{shortDate(d.date)}</td>
									<td><span class="sym">{d.symbol}</span> <span class="faint">{d.asset_name}</span></td>
									<td class="right num">{money(d.amount)}</td>
									<td class="right num muted">{money(d.tax)}</td>
									<td class="right num pos">{money(d.amount - d.tax)}</td>
									<td class="muted">{d.account_name}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="empty"><strong>No dividends recorded</strong></div>
				{/if}
			{:else}
				<div class="tab-head"><button class="btn small" onclick={() => (editAsset = null)}><Icon name="plus" size={14} /> New asset</button></div>
				{#if assets.length}
					<table class="table">
						<thead><tr><th>Symbol</th><th>Name</th><th>Type</th><th>Region</th><th>Prices from</th><th class="right">Last price</th></tr></thead>
						<tbody>
							{#each assets as a (a.id)}
								<tr class="clickable" onclick={() => (editAsset = a)}>
									<td class="sym">{a.symbol}</td>
									<td>{a.name}</td>
									<td class="muted">{ASSET_KINDS[a.kind]}</td>
									<td class="muted">{REGIONS[a.region]}</td>
									<td class="muted">{a.price_source === 'manual' ? 'By hand' : a.price_source === 'yahoo' ? `Yahoo · ${a.source_id || a.symbol}` : `CoinGecko · ${a.source_id}`}</td>
									<td class="right num">{price(a.last_price)}{#if a.last_price_date}<div class="faint small">{shortDate(a.last_price_date)}</div>{/if}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="empty"><strong>No assets yet</strong>An asset is anything you hold: an ETF, a stock, a bond fund, a coin.</div>
				{/if}
			{/if}
		</section>
		<p class="faint disclaimer">Coffer records and measures; it does not give investment advice.</p>
	{/if}
</div>

{#if editTrade !== undefined}<TradeForm trade={editTrade} {accounts} {assets} onclose={() => (editTrade = undefined)} />{/if}
{#if editDividend !== undefined}<DividendForm dividend={editDividend} {accounts} {assets} onclose={() => (editDividend = undefined)} />{/if}
{#if editAsset !== undefined}<AssetForm asset={editAsset} onclose={() => (editAsset = undefined)} />{/if}

<style>
	.stats {
		display: grid;
		grid-template-columns: 1.4fr repeat(4, 1fr);
		gap: 14px;
		margin-bottom: 16px;
	}

	.stats .display {
		font-size: 22px;
		margin-top: 6px;
	}

	.stats .big {
		font-size: 32px;
	}

	.stats p {
		font-size: 12px;
		margin-top: 2px;
	}

	.stale {
		margin-bottom: 16px;
	}

	.charts {
		display: grid;
		grid-template-columns: 1.6fr 1fr;
		gap: 16px;
		margin-bottom: 20px;
	}

	.alloc {
		display: grid;
		grid-template-columns: 180px 1fr;
		gap: 14px;
		align-items: center;
	}

	.alloc ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 8px;
		font-size: 13px;
	}

	.alloc li {
		display: grid;
		grid-template-columns: auto 1fr auto;
		gap: 9px;
		align-items: center;
	}

	.main-tabs {
		margin-bottom: 12px;
	}

	.flush {
		padding: 10px 6px;
	}

	.sym {
		font-weight: 600;
		font-family: var(--font-mono);
		font-size: 13px;
	}

	.small {
		font-size: 12px;
	}

	tr.closed td {
		opacity: 0.55;
	}

	.pill.sell {
		background: var(--neg-soft);
		color: var(--neg);
	}

	.years {
		display: flex;
		gap: 36px;
		padding: 8px 10px 18px;
	}

	.years div {
		display: grid;
		gap: 2px;
	}

	.years .display {
		font-size: 22px;
	}

	.tab-head {
		display: flex;
		justify-content: flex-end;
		padding: 4px 10px 10px;
	}

	.disclaimer {
		margin-top: 14px;
		font-size: 12px;
	}

	@media (max-width: 1150px) {
		.stats {
			grid-template-columns: repeat(3, 1fr);
		}

		.charts {
			grid-template-columns: 1fr;
		}
	}
</style>

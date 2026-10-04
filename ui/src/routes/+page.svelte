<script lang="ts">
	import { goto } from '$app/navigation';
	import { rpc } from '#lib/api.ts';
	import Chart, { tooltipBase, type ChartOption, type ThemeColors } from '#lib/components/Chart.svelte';
	import { resetTxFilters } from '#lib/filters.svelte.ts';
	import { ACCOUNT_KINDS, axisMonth, dayMonth, money, monthLabel, pct } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Overview } from '#lib/types.ts';

	let data = $state<Overview | null>(null);

	$effect(() => {
		void session.version;
		rpc<Overview>('overview')
			.then((d) => (data = d))
			.catch((e) => toasts.error(e));
	});

	let totalSpent = $derived(data ? data.spending.reduce((sum, s) => sum + s.spent, 0) : 0);

	function seriesOption(d: Overview) {
		return (c: ThemeColors): ChartOption => ({
			grid: { left: 8, right: 8, top: 16, bottom: 4, containLabel: true },
			tooltip: {
				...tooltipBase(),
				trigger: 'axis',
				formatter: (items: { dataIndex: number }[]) => {
					const p = d.series[items[0].dataIndex];
					return `<b>${monthLabel(p.date.slice(0, 7))}</b><br/>Net worth ${money(p.net_worth)}<br/><span style="opacity:.7">Cash ${money(p.cash)} · Invested ${money(p.investments)}</span>`;
				}
			},
			xAxis: {
				type: 'category',
				data: d.series.map((p) => p.date),
				axisLine: { lineStyle: { color: c.line } },
				axisTick: { show: false },
				axisLabel: { color: c.faint, fontSize: 11, formatter: axisMonth }
			},
			yAxis: {
				type: 'value',
				splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
				axisLabel: { color: c.faint, fontSize: 11, formatter: (v: number) => money(v, { compact: true }) }
			},
			series: [
				{
					name: 'Cash',
					type: 'line',
					stack: 'total',
					symbol: 'none',
					smooth: 0.25,
					lineStyle: { width: 0 },
					areaStyle: { color: c.pos, opacity: 0.22 },
					data: d.series.map((p) => p.cash)
				},
				{
					name: 'Investments',
					type: 'line',
					stack: 'total',
					symbol: 'none',
					smooth: 0.25,
					lineStyle: { width: 2, color: c.accent },
					areaStyle: { color: c.accent, opacity: 0.2 },
					data: d.series.map((p) => p.investments)
				}
			]
		});
	}

	function spendingOption(d: Overview) {
		return (c: ThemeColors): ChartOption => ({
			tooltip: { ...tooltipBase(), formatter: (p: { name: string; value: number; percent: number }) => `${p.name}<br/><b>${money(p.value)}</b> · ${p.percent}%` },
			series: [
				{
					type: 'pie',
					radius: ['62%', '88%'],
					padAngle: 2,
					itemStyle: { borderRadius: 4, borderColor: c.surface, borderWidth: 0 },
					label: { show: false },
					data: d.spending.map((s) => ({ name: s.name, value: s.spent, itemStyle: { color: s.color } }))
				}
			]
		});
	}

	function showCategory(id: number | null) {
		resetTxFilters({ category_id: id === null ? 'none' : String(id), from: `${data!.month}-01` });
		goto('#/transactions');
	}
</script>

<div class="page">
	<header class="page-head">
		<div>
			<h1>Overview</h1>
			<p>{data ? monthLabel(data.month) : ''}</p>
		</div>
		<div class="actions">
			<a class="btn" href="#/transactions">All transactions</a>
		</div>
	</header>

	{#if data}
		<section class="hero card">
			<div class="worth">
				<h3>Net worth</h3>
				<div class="display big num">{money(data.net_worth)}</div>
				{#if data.change_this_month !== null}
					<p class="num" class:pos={data.change_this_month >= 0} class:neg={data.change_this_month < 0}>
						{money(data.change_this_month, { sign: true })} <span class="muted">since the end of last month</span>
					</p>
				{/if}
				<dl>
					<div><dt>Cash</dt><dd class="num">{money(data.cash)}</dd></div>
					<div><dt>Investments</dt><dd class="num">{money(data.investments)}</dd></div>
				</dl>
			</div>
			<div class="chart">
				{#if data.series.length > 1}
					<Chart height={230} option={seriesOption(data)} />
				{:else}
					<p class="empty">The chart appears once there is more than a month of history.</p>
				{/if}
			</div>
		</section>

		<section class="stats">
			<div class="card stat">
				<h3>Money in this month</h3>
				<div class="display num">{money(data.income)}</div>
			</div>
			<div class="card stat">
				<h3>Money out this month</h3>
				<div class="display num">{money(data.expenses)}</div>
			</div>
			<div class="card stat">
				<h3>Saved</h3>
				<div class="display num" class:pos={data.income - data.expenses > 0} class:neg={data.income - data.expenses < 0}>
					{money(data.income - data.expenses, { sign: true })}
				</div>
				<p class="muted">{data.savings_rate !== null ? `${pct(data.savings_rate, { digits: 0 })} of income` : 'No income yet this month'}</p>
			</div>
		</section>

		<section class="columns">
			<div class="card">
				<div class="card-head"><h2>Spending this month</h2><span class="muted num">{money(totalSpent)}</span></div>
				{#if data.spending.length}
					<div class="spending">
						<Chart height={190} option={spendingOption(data)} />
						<ul class="legend">
							{#each data.spending.slice(0, 7) as slice (slice.name)}
								<li>
									<button onclick={() => showCategory(slice.id)}>
										<i class="dot" style:background={slice.color}></i>
										<span>{slice.name}</span>
										<span class="num">{money(slice.spent)}</span>
									</button>
								</li>
							{/each}
						</ul>
					</div>
				{:else}
					<p class="empty">No spending recorded this month.</p>
				{/if}
			</div>

			<div class="card">
				<div class="card-head"><h2>Budgets</h2><a class="btn small ghost" href="#/budget">Open budget</a></div>
				{#if data.budgets.length}
					<ul class="budgets">
						{#each data.budgets as line (line.category_id)}
							{@const used = line.used ?? 0}
							<li>
								<div class="line">
									<span>{line.name}</span>
									<span class="num muted"><b class:neg={used > 1}>{money(line.spent)}</b> of {money(line.budget)}</span>
								</div>
								<div class="bar">
									<i style:width="{Math.min(used, 1) * 100}%" style:background={used > 1 ? 'var(--neg)' : used > data.progress + 0.1 ? 'var(--warn)' : line.color}></i>
								</div>
							</li>
						{/each}
					</ul>
					<p class="faint pace">{pct(data.progress, { digits: 0 })} of the month has gone by.</p>
				{:else}
					<p class="empty">Set monthly budgets on the Budget page.</p>
				{/if}
			</div>
		</section>

		<section class="columns">
			<div class="card">
				<div class="card-head"><h2>Recent</h2></div>
				{#if data.recent.length}
					<table class="table">
						<tbody>
							{#each data.recent as tx (tx.id)}
								<tr>
									<td class="muted num date">{dayMonth(tx.date)}</td>
									<td>
										<div class="payee">{tx.payee}</div>
										<div class="faint small">{tx.account_name}</div>
									</td>
									<td>
										{#if tx.transfer_group}
											<span class="pill">Transfer</span>
										{:else if tx.category_name}
											<span class="pill"><i class="dot" style:background={tx.category_color}></i>{tx.category_name}</span>
										{/if}
									</td>
									<td class="right num" class:pos={tx.amount > 0}>{money(tx.amount)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="empty"><strong>No transactions yet</strong>Add an account, then import a statement or add transactions by hand.</div>
				{/if}
			</div>

			<div class="card">
				<div class="card-head"><h2>Accounts</h2><a class="btn small ghost" href="#/accounts">Manage</a></div>
				{#if data.accounts.length}
					<ul class="accounts">
						{#each data.accounts as account (account.id)}
							<li>
								<div>
									<div>{account.name}</div>
									<div class="faint small">{ACCOUNT_KINDS[account.kind]}{account.institution ? ` · ${account.institution}` : ''}</div>
								</div>
								<span class="num" class:neg={account.balance < 0}>{money(account.balance)}</span>
							</li>
						{/each}
					</ul>
				{:else}
					<div class="empty"><strong>No accounts</strong><a href="#/accounts">Add your first account</a></div>
				{/if}
			</div>
		</section>
	{/if}
</div>

<style>
	.hero {
		display: grid;
		grid-template-columns: minmax(240px, 300px) 1fr;
		gap: 28px;
		padding: 24px;
	}

	.big {
		font-size: 44px;
		line-height: 1.1;
		margin: 6px 0 6px;
	}

	dl {
		display: grid;
		gap: 10px;
		margin: 22px 0 0;
		padding-top: 16px;
		border-top: 1px solid var(--line);
	}

	dl div {
		display: flex;
		justify-content: space-between;
	}

	dt {
		color: var(--muted);
	}

	dd {
		margin: 0;
	}

	.chart {
		min-width: 0;
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 16px;
		margin: 16px 0;
	}

	.stat .display {
		font-size: 26px;
		margin-top: 6px;
	}

	.stat p {
		font-size: 12px;
		margin-top: 2px;
	}

	.columns {
		display: grid;
		grid-template-columns: 1.25fr 1fr;
		gap: 16px;
		margin-bottom: 16px;
	}

	.spending {
		display: grid;
		grid-template-columns: 190px 1fr;
		gap: 18px;
		align-items: center;
	}

	.legend,
	.budgets,
	.accounts {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.legend button {
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: center;
		gap: 9px;
		width: 100%;
		padding: 6px 8px;
		border: 0;
		background: none;
		border-radius: 6px;
		cursor: pointer;
		text-align: left;
	}

	.legend button:hover {
		background: var(--surface-2);
	}

	.budgets {
		display: grid;
		gap: 14px;
	}

	.line {
		display: flex;
		justify-content: space-between;
		margin-bottom: 6px;
		font-size: 13px;
	}

	.line b {
		font-weight: 600;
		color: var(--text);
	}

	.pace {
		margin-top: 14px;
		font-size: 12px;
	}

	.accounts li {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 10px 0;
		border-bottom: 1px solid var(--line);
	}

	.accounts li:last-child {
		border-bottom: 0;
	}

	.small {
		font-size: 12px;
	}

	.date {
		width: 70px;
	}

	.payee {
		max-width: 260px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	@media (max-width: 1100px) {
		.hero,
		.columns {
			grid-template-columns: 1fr;
		}
	}
</style>

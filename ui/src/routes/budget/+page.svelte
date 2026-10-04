<script lang="ts">
	import { goto } from '$app/navigation';
	import { rpc } from '#lib/api.ts';
	import Chart, { tooltipBase, type ThemeColors } from '#lib/components/Chart.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import MoneyInput from '#lib/components/MoneyInput.svelte';
	import { resetTxFilters } from '#lib/filters.svelte.ts';
	import { axisMonth, money, monthLabel, pct, shiftMonth, today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { BudgetLine, BudgetReport, CashFlowMonth, Category } from '#lib/types.ts';

	const thisMonth = today().slice(0, 7);
	let month = $state(thisMonth);
	let report = $state<BudgetReport | null>(null);
	let flow = $state<CashFlowMonth[]>([]);
	let categories = $state<Category[]>([]);
	let editingId = $state<number | null>(null);
	let draft = $state<number | null>(null);

	$effect(() => {
		void session.version;
		rpc<BudgetReport>('budget_report', { month })
			.then((r) => (report = r))
			.catch((e) => toasts.error(e));
	});

	$effect(() => {
		void session.version;
		Promise.all([rpc<CashFlowMonth[]>('cash_flow', { months: 12 }), rpc<Category[]>('list_categories')])
			.then(([f, c]) => {
				flow = f;
				categories = c;
			})
			.catch((e) => toasts.error(e));
	});

	let budgeted = $derived(report?.lines.filter((l) => l.budget !== null) ?? []);
	let unbudgeted = $derived(report?.lines.filter((l) => l.budget === null) ?? []);

	function startEdit(line: BudgetLine) {
		editingId = line.category_id;
		draft = line.budget ?? line.average_3m ?? null;
	}

	async function saveBudget(line: BudgetLine, value: number | null) {
		const category = categories.find((c) => c.id === line.category_id);
		if (!category) return;
		try {
			await rpc('save_category', { category: { ...category, monthly_budget: value } });
			editingId = null;
			session.changed();
		} catch (err) {
			toasts.error(err);
		}
	}

	function openCategory(id: number | null) {
		resetTxFilters({ category_id: id === null ? 'none' : String(id), from: `${month}-01`, to: lastDay(month) });
		goto('#/transactions');
	}

	function lastDay(m: string) {
		const [y, mo] = m.split('-').map(Number);
		return `${m}-${String(new Date(y, mo, 0).getDate()).padStart(2, '0')}`;
	}

	function barColor(line: BudgetLine, progress: number) {
		const used = line.used ?? 0;
		if (used > 1) return 'var(--neg)';
		if (used > progress + 0.15 && progress < 1) return 'var(--warn)';
		return line.color;
	}

	function flowOption(c: ThemeColors) {
		return {
			grid: { left: 8, right: 8, top: 26, bottom: 4, containLabel: true },
			legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: c.muted, fontSize: 12 } },
			tooltip: {
				...tooltipBase(),
				trigger: 'axis',
				formatter: (items: { dataIndex: number }[]) => {
					const m = flow[items[0].dataIndex];
					return `<b>${monthLabel(m.month)}</b><br/>In ${money(m.income)}<br/>Out ${money(m.expenses)}<br/>Net <b>${money(m.net, { sign: true })}</b>`;
				}
			},
			xAxis: {
				type: 'category',
				data: flow.map((m) => m.month),
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
				{ name: 'In', type: 'bar', barGap: '15%', barMaxWidth: 16, itemStyle: { color: c.pos, borderRadius: [3, 3, 0, 0] }, data: flow.map((m) => m.income) },
				{ name: 'Out', type: 'bar', barMaxWidth: 16, itemStyle: { color: c.neg, opacity: 0.85, borderRadius: [3, 3, 0, 0] }, data: flow.map((m) => m.expenses) }
			]
		};
	}
</script>

<div class="page">
	<header class="page-head">
		<div>
			<h1>Budget</h1>
			<p>Monthly limits per category, and how the month is going.</p>
		</div>
		<div class="month">
			<button class="btn small" onclick={() => (month = shiftMonth(month, -1))} aria-label="Previous month"><Icon name="left" size={16} /></button>
			<strong>{monthLabel(month)}</strong>
			<button class="btn small" onclick={() => (month = shiftMonth(month, 1))} disabled={month >= thisMonth} aria-label="Next month"><Icon name="right" size={16} /></button>
		</div>
	</header>

	{#if report}
		<section class="summary">
			<div class="card"><h3>Money in</h3><div class="display num">{money(report.totals.income)}</div></div>
			<div class="card"><h3>Money out</h3><div class="display num">{money(report.totals.expenses)}</div></div>
			<div class="card">
				<h3>Saved</h3>
				<div class="display num" class:pos={report.totals.saved > 0} class:neg={report.totals.saved < 0}>{money(report.totals.saved, { sign: true })}</div>
			</div>
			<div class="card"><h3>Savings rate</h3><div class="display num">{pct(report.totals.savings_rate, { digits: 0 })}</div></div>
		</section>

		<section class="card">
			<div class="card-head">
				<h2>Budgets</h2>
				<span class="muted num">
					{money(report.totals.spent_in_budgets)} of {money(report.totals.budget)}
					{#if report.progress > 0 && report.progress < 1}· {pct(report.progress, { digits: 0 })} of the month gone{/if}
				</span>
			</div>
			{#if budgeted.length}
				<ul class="lines">
					{#each budgeted as line (line.category_id)}
						<li>
							<button class="name" onclick={() => openCategory(line.category_id)}>
								<i class="dot" style:background={line.color}></i>{line.name}
							</button>
							<div class="track">
								<div class="bar big">
									<i style:width="{Math.min(line.used ?? 0, 1) * 100}%" style:background={barColor(line, report.progress)}></i>
								</div>
								{#if report.progress > 0 && report.progress < 1}
									<span class="pace" style:left="{report.progress * 100}%" title="Share of the month gone"></span>
								{/if}
							</div>
							<span class="num spent"><b class:neg={(line.used ?? 0) > 1}>{money(line.spent)}</b></span>
							{#if editingId === line.category_id}
								<form class="edit" onsubmit={(e) => (e.preventDefault(), saveBudget(line, draft))}>
									<MoneyInput bind:value={draft} />
									<button class="btn small primary">Save</button>
									<button class="btn small ghost" type="button" onclick={() => saveBudget(line, null)}>Remove</button>
								</form>
							{:else}
								<button class="budget num" onclick={() => startEdit(line)} title="Change budget">of {money(line.budget)}</button>
								<span class="num left" class:neg={(line.remaining ?? 0) < 0}>
									{(line.remaining ?? 0) >= 0 ? `${money(line.remaining)} left` : `${money(-(line.remaining ?? 0))} over`}
								</span>
							{/if}
						</li>
					{/each}
				</ul>
			{:else}
				<p class="empty">No budgets yet. Pick a category below and set a monthly limit.</p>
			{/if}
		</section>

		<section class="columns">
			<div class="card">
				<div class="card-head"><h2>Other spending</h2><span class="faint">no budget set</span></div>
				<table class="table">
					<thead><tr><th>Category</th><th class="right">This month</th><th class="right">3-month average</th><th></th></tr></thead>
					<tbody>
						{#each unbudgeted as line (line.category_id)}
							<tr>
								<td><button class="name" onclick={() => openCategory(line.category_id)}><i class="dot" style:background={line.color}></i>{line.name}</button></td>
								<td class="right num">{money(line.spent)}</td>
								<td class="right num muted">{money(line.average_3m)}</td>
								<td class="right">
									{#if editingId === line.category_id}
										<form class="edit inline" onsubmit={(e) => (e.preventDefault(), saveBudget(line, draft))}>
											<MoneyInput bind:value={draft} />
											<button class="btn small primary">Set</button>
										</form>
									{:else}
										<button class="btn small ghost" onclick={() => startEdit(line)}>Set budget</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
				{#if report.uncategorized > 0}
					<button class="notice uncat" onclick={() => openCategory(null)}>
						{money(report.uncategorized)} of spending this month has no category. Categorize it →
					</button>
				{/if}
			</div>

			<div class="card">
				<div class="card-head"><h2>Last 12 months</h2></div>
				{#if flow.length}<Chart height={300} option={flowOption} />{/if}
			</div>
		</section>
	{/if}
</div>

<style>
	.month {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.month strong {
		min-width: 130px;
		text-align: center;
		font-weight: 600;
	}

	.summary {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-bottom: 16px;
	}

	.summary .display {
		font-size: 24px;
		margin-top: 6px;
	}

	.lines {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.lines li {
		display: grid;
		grid-template-columns: 170px 1fr 100px 260px;
		align-items: center;
		gap: 16px;
		padding: 11px 0;
		border-bottom: 1px solid var(--line);
	}

	.lines li:last-child {
		border-bottom: 0;
	}

	.lines li > .budget,
	.lines li > .left {
		grid-column: 4;
		grid-row: 1;
	}

	.lines li > .budget {
		justify-self: start;
	}

	.lines li > .left {
		justify-self: end;
		font-size: 13px;
		color: var(--muted);
	}

	.lines li > .left.neg {
		color: var(--neg);
	}

	.name {
		display: inline-flex;
		align-items: center;
		gap: 9px;
		border: 0;
		background: none;
		padding: 0;
		cursor: pointer;
		text-align: left;
	}

	.name:hover {
		text-decoration: underline;
	}

	.track {
		position: relative;
	}

	.bar.big {
		height: 8px;
	}

	.pace {
		position: absolute;
		top: -4px;
		width: 2px;
		height: 16px;
		background: var(--muted);
		opacity: 0.6;
		border-radius: 2px;
	}

	.spent {
		text-align: right;
	}

	.spent b {
		font-weight: 600;
	}

	.budget {
		border: 0;
		background: none;
		color: var(--muted);
		cursor: pointer;
		padding: 2px 4px;
		border-radius: 5px;
	}

	.budget:hover {
		background: var(--surface-3);
		color: var(--text);
	}

	.edit {
		grid-column: 4;
		display: flex;
		gap: 6px;
		align-items: center;
	}

	.edit :global(.money-input) {
		width: 120px;
	}

	.edit :global(input) {
		height: 28px;
	}

	.edit.inline {
		justify-content: flex-end;
	}

	.columns {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 16px;
		margin-top: 16px;
	}

	.uncat {
		width: 100%;
		margin-top: 14px;
		border: 0;
		cursor: pointer;
		text-align: left;
	}

	@media (max-width: 1150px) {
		.columns {
			grid-template-columns: 1fr;
		}

		.lines li {
			grid-template-columns: 140px 1fr 90px 230px;
		}
	}
</style>

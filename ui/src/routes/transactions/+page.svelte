<script lang="ts">
	import { rpc } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import TransactionForm from '#lib/components/forms/TransactionForm.svelte';
	import TransferForm from '#lib/components/forms/TransferForm.svelte';
	import { resetTxFilters, txFilters } from '#lib/filters.svelte.ts';
	import { money, shortDate } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account, Category, Transaction, TransactionPage } from '#lib/types.ts';

	const PAGE = 100;

	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let data = $state<TransactionPage | null>(null);
	let limit = $state(PAGE);
	let editing = $state<Transaction | null | undefined>(undefined);
	let transferring = $state(false);
	let search = $state(txFilters.search);

	$effect(() => {
		void session.version;
		Promise.all([rpc<Account[]>('list_accounts'), rpc<Category[]>('list_categories')])
			.then(([a, c]) => {
				accounts = a;
				categories = c;
			})
			.catch((e) => toasts.error(e));
	});

	$effect(() => {
		void session.version;
		const query = {
			account_id: txFilters.account_id ? Number(txFilters.account_id) : null,
			category_id: txFilters.category_id === 'none' || txFilters.category_id === 'transfer' ? txFilters.category_id : txFilters.category_id ? Number(txFilters.category_id) : null,
			search: txFilters.search,
			from: txFilters.from || null,
			to: txFilters.to || null,
			limit
		};
		rpc<TransactionPage>('list_transactions', { query })
			.then((d) => (data = d))
			.catch((e) => toasts.error(e));
	});

	// Search as you type, without a request per keystroke.
	$effect(() => {
		const value = search;
		const timer = setTimeout(() => (txFilters.search = value), 250);
		return () => clearTimeout(timer);
	});

	let filtered = $derived(!!(txFilters.account_id || txFilters.category_id || txFilters.search || txFilters.from || txFilters.to));
	let income = $derived(categories.filter((c) => c.kind === 'income'));
	let expense = $derived(categories.filter((c) => c.kind === 'expense'));

	async function setCategory(tx: Transaction, value: string) {
		try {
			await rpc('save_transaction', { transaction: { ...tx, category_id: value ? Number(value) : null } });
			session.changed();
		} catch (err) {
			toasts.error(err);
			session.changed();
		}
	}

	function clear() {
		search = '';
		resetTxFilters();
	}
</script>

<div class="page">
	<header class="page-head">
		<div>
			<h1>Transactions</h1>
			<p>Everything that moved in or out of your accounts.</p>
		</div>
		<div class="actions">
			<button class="btn" onclick={() => (transferring = true)} disabled={accounts.length < 2}>Transfer</button>
			<button class="btn primary" onclick={() => (editing = null)} disabled={!accounts.length}><Icon name="plus" size={16} /> New transaction</button>
		</div>
	</header>

	<div class="filters">
		<label class="search">
			<Icon name="search" size={16} />
			<input class="input" placeholder="Search payee or note" bind:value={search} />
		</label>
		<select class="input" bind:value={txFilters.account_id} aria-label="Account">
			<option value="">All accounts</option>
			{#each accounts as a (a.id)}<option value={String(a.id)}>{a.name}</option>{/each}
		</select>
		<select class="input" bind:value={txFilters.category_id} aria-label="Category">
			<option value="">All categories</option>
			<option value="none">Uncategorized</option>
			<option value="transfer">Transfers</option>
			<optgroup label="Income">{#each income as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}</optgroup>
			<optgroup label="Spending">{#each expense as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}</optgroup>
		</select>
		<input class="input date" type="date" bind:value={txFilters.from} aria-label="From" />
		<input class="input date" type="date" bind:value={txFilters.to} aria-label="To" />
		{#if filtered}<button class="btn ghost" onclick={clear}>Clear</button>{/if}
	</div>

	{#if data}
		<div class="summary">
			<span>{data.total} transactions</span>
			<span>In <b class="num pos">{money(data.income)}</b></span>
			<span>Out <b class="num">{money(-data.expenses)}</b></span>
		</div>

		<div class="card flush">
			{#if data.items.length}
				<table class="table">
					<thead>
						<tr>
							<th>Date</th>
							<th>Description</th>
							<th>Category</th>
							<th>Account</th>
							<th class="right">Amount</th>
						</tr>
					</thead>
					<tbody>
						{#each data.items as tx (tx.id)}
							<tr class="clickable" onclick={() => (editing = tx)}>
								<td class="muted num date">{shortDate(tx.date)}</td>
								<td>
									<div class="payee">{tx.payee}</div>
									{#if tx.note}<div class="faint note">{tx.note}</div>{/if}
								</td>
								<td onclick={(e) => e.stopPropagation()}>
									{#if tx.transfer_group}
										<span class="pill">↔ {tx.counter_account_name}</span>
									{:else}
										<div class="cat">
											<i class="dot" style:background={tx.category_color ?? 'var(--line-strong)'}></i>
											<select value={tx.category_id === null ? '' : String(tx.category_id)} onchange={(e) => setCategory(tx, (e.target as HTMLSelectElement).value)} class:unset={tx.category_id === null} aria-label="Category">
												<option value="">Uncategorized</option>
												{#if tx.amount > 0}
													<optgroup label="Income">{#each income as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}</optgroup>
													<optgroup label="Refund of spending">{#each expense as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}</optgroup>
												{:else}
													{#each expense as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}
												{/if}
											</select>
										</div>
									{/if}
								</td>
								<td class="muted">{tx.account_name}</td>
								<td class="right num amount" class:pos={tx.amount > 0}>{money(tx.amount, { sign: true })}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				{#if data.items.length < data.total}
					<div class="more"><button class="btn" onclick={() => (limit += PAGE)}>Show {Math.min(PAGE, data.total - data.items.length)} more</button></div>
				{/if}
			{:else}
				<div class="empty">
					<strong>{filtered ? 'Nothing matches these filters' : 'No transactions yet'}</strong>
					{filtered ? 'Try clearing a filter.' : 'Add one by hand or import a bank statement.'}
				</div>
			{/if}
		</div>
	{/if}
</div>

{#if editing !== undefined}
	<TransactionForm
		transaction={editing}
		{accounts}
		{categories}
		defaultAccount={txFilters.account_id ? Number(txFilters.account_id) : undefined}
		onclose={() => (editing = undefined)}
	/>
{/if}
{#if transferring}
	<TransferForm {accounts} onclose={() => (transferring = false)} />
{/if}

<style>
	.filters {
		display: flex;
		gap: 8px;
		margin-bottom: 14px;
		flex-wrap: wrap;
	}

	.filters select {
		width: 180px;
	}

	.filters .date {
		width: 150px;
	}

	.search {
		position: relative;
		flex: 1;
		min-width: 220px;
	}

	.search :global(svg) {
		position: absolute;
		left: 11px;
		top: 10px;
		color: var(--faint);
	}

	.search input {
		padding-left: 34px;
	}

	.summary {
		display: flex;
		gap: 22px;
		color: var(--muted);
		font-size: 13px;
		margin: 0 4px 10px;
	}

	.summary b {
		font-weight: 600;
		color: var(--text);
	}

	.summary b.pos {
		color: var(--pos);
	}

	.flush {
		padding: 8px 6px;
	}

	.table th {
		padding-top: 8px;
	}

	.date {
		width: 110px;
	}

	.payee {
		max-width: 360px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.note {
		font-size: 12px;
	}

	.amount {
		font-weight: 500;
	}

	.cat {
		display: flex;
		align-items: center;
		gap: 7px;
	}

	.cat select {
		border: 1px solid transparent;
		background: transparent;
		border-radius: 6px;
		padding: 3px 4px;
		max-width: 170px;
		cursor: pointer;
	}

	.cat select:hover {
		border-color: var(--line-strong);
		background: var(--surface-2);
	}

	.cat select.unset {
		color: var(--warn);
	}

	.more {
		display: flex;
		justify-content: center;
		padding: 14px;
	}
</style>

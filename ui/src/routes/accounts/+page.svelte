<script lang="ts">
	import { goto } from '$app/navigation';
	import { rpc } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import AccountForm from '#lib/components/forms/AccountForm.svelte';
	import { resetTxFilters } from '#lib/filters.svelte.ts';
	import { ACCOUNT_KINDS, money, shortDate } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account } from '#lib/types.ts';

	let accounts = $state<Account[] | null>(null);
	let editing = $state<Partial<Account> | null | undefined>(undefined);

	$effect(() => {
		void session.version;
		rpc<Account[]>('list_accounts')
			.then((a) => (accounts = a))
			.catch((e) => toasts.error(e));
	});

	let open = $derived((accounts ?? []).filter((a) => !a.archived));
	let archived = $derived((accounts ?? []).filter((a) => a.archived));
	let assets = $derived(open.filter((a) => a.balance > 0).reduce((s, a) => s + a.balance, 0));
	let debts = $derived(open.filter((a) => a.balance < 0).reduce((s, a) => s + a.balance, 0));

	function showTransactions(account: Account) {
		resetTxFilters({ account_id: String(account.id) });
		goto('#/transactions');
	}
</script>

<div class="page">
	<header class="page-head">
		<div>
			<h1>Accounts</h1>
			<p>Cash held in each account. Investment holdings are on the Investments page.</p>
		</div>
		<div class="actions">
			<button class="btn primary" onclick={() => (editing = null)}><Icon name="plus" size={16} /> New account</button>
		</div>
	</header>

	{#if accounts}
		{#if open.length}
			<div class="totals">
				<div><h3>Positive balances</h3><span class="display num">{money(assets)}</span></div>
				<div><h3>Owed</h3><span class="display num" class:neg={debts < 0}>{money(debts)}</span></div>
				<div><h3>Net cash</h3><span class="display num">{money(assets + debts)}</span></div>
			</div>
			<div class="cards">
				{#each open as account (account.id)}
					<article class="card account">
						<header>
							<span class="pill">{ACCOUNT_KINDS[account.kind]}</span>
							<button class="btn ghost small" onclick={() => (editing = account)}>Edit</button>
						</header>
						<h2>{account.name}</h2>
						<p class="faint">{account.institution || 'No provider set'}</p>
						<div class="balance display num" class:neg={account.balance < 0}>{money(account.balance)}</div>
						<footer>
							<span class="faint">{account.movements} movements · since {shortDate(account.opening_date)}</span>
							<button class="btn small" onclick={() => showTransactions(account)}>Transactions</button>
						</footer>
					</article>
				{/each}
			</div>
		{:else}
			<div class="card empty">
				<strong>No accounts yet</strong>
				Start with your main current account. You can import its statement afterwards.
				<div style="margin-top:16px"><button class="btn primary" onclick={() => (editing = null)}>Add an account</button></div>
			</div>
		{/if}

		{#if archived.length}
			<h2 class="section">Archived</h2>
			<div class="card">
				<table class="table">
					<tbody>
						{#each archived as account (account.id)}
							<tr class="clickable" onclick={() => (editing = account)}>
								<td>{account.name}</td>
								<td class="muted">{ACCOUNT_KINDS[account.kind]}</td>
								<td class="right num">{money(account.balance)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{/if}
</div>

{#if editing !== undefined}
	<AccountForm account={editing} onclose={() => (editing = undefined)} />
{/if}

<style>
	.totals {
		display: flex;
		gap: 40px;
		margin-bottom: 20px;
	}

	.totals .display {
		font-size: 24px;
	}

	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 16px;
	}

	.account header,
	.account footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
	}

	.account h2 {
		margin-top: 14px;
		font-size: 17px;
	}

	.account p {
		font-size: 13px;
	}

	.balance {
		font-size: 30px;
		margin: 18px 0;
	}

	.account footer {
		padding-top: 14px;
		border-top: 1px solid var(--line);
		font-size: 12px;
	}

	.section {
		margin: 30px 0 12px;
	}
</style>

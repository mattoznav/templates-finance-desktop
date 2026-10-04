<script lang="ts">
	import { untrack } from 'svelte';
	import { rpc } from '#lib/api.ts';
	import { confirmAction } from '#lib/confirm.svelte.ts';
	import { money, shortDate, today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account, Category, Transaction } from '#lib/types.ts';
	import Modal from '../Modal.svelte';
	import MoneyInput from '../MoneyInput.svelte';

	interface Props {
		transaction: Transaction | null;
		accounts: Account[];
		categories: Category[];
		defaultAccount?: number;
		onclose: () => void;
	}

	let { transaction, accounts, categories, defaultAccount, onclose }: Props = $props();

	const isTransfer = untrack(() => !!transaction?.transfer_group);
	let direction = $state<'out' | 'in'>(untrack(() => (transaction && transaction.amount > 0 ? 'in' : 'out')));
	let amount = $state<number | null>(untrack(() => (transaction ? Math.abs(transaction.amount) : null)));
	let form = $state(
		untrack(() => ({
			id: transaction?.id,
			account_id: transaction?.account_id ?? defaultAccount ?? accounts.find((a) => !a.archived)?.id,
			date: transaction?.date ?? today(),
			payee: transaction?.payee ?? '',
			category_id: transaction?.category_id ?? null,
			note: transaction?.note ?? ''
		}))
	);
	let busy = $state(false);

	let income = $derived(categories.filter((c) => c.kind === 'income'));
	let expense = $derived(categories.filter((c) => c.kind === 'expense'));

	$effect(() => {
		// An income category cannot hold money going out.
		if (direction === 'out' && income.some((c) => c.id === form.category_id)) form.category_id = null;
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!amount) return;
		busy = true;
		try {
			await rpc('save_transaction', {
				transaction: { ...form, amount: direction === 'out' ? -amount : amount }
			});
			toasts.show(form.id ? 'Transaction updated' : 'Transaction added');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		const ok = await confirmAction({
			title: 'Delete this transaction?',
			message: isTransfer ? 'Both sides of the transfer will be removed.' : `${transaction!.payee}, ${money(transaction!.amount)} on ${shortDate(transaction!.date)}.`,
			confirm: 'Delete',
			danger: true
		});
		if (!ok) return;
		try {
			await rpc('delete_transaction', { id: transaction!.id });
			toasts.show('Transaction deleted');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		}
	}
</script>

{#if isTransfer && transaction}
	<Modal title="Transfer" subtitle={shortDate(transaction.date)} {onclose} width={440}>
		<p>
			<span class="num">{money(Math.abs(transaction.amount))}</span>
			{transaction.amount < 0 ? 'from' : 'to'} <b>{transaction.account_name}</b>
			{transaction.amount < 0 ? 'to' : 'from'} <b>{transaction.counter_account_name}</b>.
		</p>
		{#if transaction.note}<p class="muted">{transaction.note}</p>{/if}
		<p class="faint">Transfers are not income or spending. To change one, delete it and record it again.</p>
		{#snippet footer()}
			<button class="btn danger" onclick={remove}>Delete transfer</button>
			<span style="flex:1"></span>
			<button class="btn" onclick={onclose}>Close</button>
		{/snippet}
	</Modal>
{:else}
	<Modal title={form.id ? 'Edit transaction' : 'New transaction'} {onclose}>
		<form id="tx-form" class="grid" onsubmit={save}>
			<div class="tabs" role="group" aria-label="Direction">
				<button type="button" class:active={direction === 'out'} onclick={() => (direction = 'out')}>Money out</button>
				<button type="button" class:active={direction === 'in'} onclick={() => (direction = 'in')}>Money in</button>
			</div>
			<div class="row">
				<label class="field"><span>Amount</span><MoneyInput bind:value={amount} /></label>
				<label class="field"><span>Date</span><input class="input" type="date" bind:value={form.date} required /></label>
			</div>
			<label class="field">
				<span>{direction === 'out' ? 'Paid to' : 'Received from'}</span>
				<input class="input" bind:value={form.payee} placeholder={direction === 'out' ? 'Greenmarket' : 'Employer'} required />
			</label>
			<div class="row">
				<label class="field">
					<span>Account</span>
					<select class="input" bind:value={form.account_id}>
						{#each accounts.filter((a) => !a.archived || a.id === form.account_id) as account (account.id)}
							<option value={account.id}>{account.name}</option>
						{/each}
					</select>
				</label>
				<label class="field">
					<span>Category</span>
					<select class="input" bind:value={form.category_id}>
						<option value={null}>Uncategorized</option>
						{#if direction === 'in'}
							<optgroup label="Income">
								{#each income as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
							</optgroup>
							<optgroup label="Refund of spending">
								{#each expense as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
							</optgroup>
						{:else}
							{#each expense as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
						{/if}
					</select>
				</label>
			</div>
			<label class="field"><span>Note</span><input class="input" bind:value={form.note} placeholder="Optional" /></label>
		</form>
		{#snippet footer()}
			{#if form.id}<button class="btn danger" type="button" onclick={remove}>Delete</button><span style="flex:1"></span>{/if}
			<button class="btn" type="button" onclick={onclose}>Cancel</button>
			<button class="btn primary" form="tx-form" disabled={busy || !amount || !form.payee.trim() || !form.account_id}>Save</button>
		{/snippet}
	</Modal>
{/if}

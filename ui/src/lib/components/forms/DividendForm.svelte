<script lang="ts">
	import { untrack } from 'svelte';
	import { rpc } from '#lib/api.ts';
	import { confirmAction } from '#lib/confirm.svelte.ts';
	import { money, today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account, Asset, Dividend } from '#lib/types.ts';
	import Modal from '../Modal.svelte';
	import MoneyInput from '../MoneyInput.svelte';

	interface Props {
		dividend: Dividend | null;
		accounts: Account[];
		assets: Asset[];
		onclose: () => void;
	}

	let { dividend, accounts, assets, onclose }: Props = $props();
	let brokers = $derived(accounts.filter((a) => a.kind === 'brokerage' || a.id === dividend?.account_id));

	let form = $state(
		untrack(() => ({
			id: dividend?.id,
			account_id: dividend?.account_id ?? accounts.find((a) => a.kind === 'brokerage')?.id,
			asset_id: dividend?.asset_id ?? assets[0]?.id,
			date: dividend?.date ?? today(),
			amount: dividend?.amount ?? (null as number | null),
			tax: dividend?.tax ?? 0,
			note: dividend?.note ?? ''
		}))
	);
	let busy = $state(false);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		try {
			await rpc('save_dividend', { dividend: { ...form, tax: form.tax ?? 0 } });
			toasts.show('Dividend saved');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!(await confirmAction({ title: 'Delete this dividend?', message: 'The cash it added is removed from the account.', confirm: 'Delete', danger: true }))) return;
		try {
			await rpc('delete_dividend', { id: form.id });
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		}
	}
</script>

<Modal title={form.id ? 'Edit dividend' : 'Record a dividend'} subtitle="The net amount is added to the account's cash." {onclose}>
	<form id="dividend-form" class="grid" onsubmit={save}>
		<div class="row">
			<label class="field"><span>Asset</span>
				<select class="input" bind:value={form.asset_id}>
					{#each assets as a (a.id)}<option value={a.id}>{a.symbol} · {a.name}</option>{/each}
				</select>
			</label>
			<label class="field"><span>Account</span>
				<select class="input" bind:value={form.account_id}>
					{#each brokers as a (a.id)}<option value={a.id}>{a.name}</option>{/each}
				</select>
			</label>
		</div>
		<div class="row">
			<label class="field"><span>Gross amount</span><MoneyInput bind:value={form.amount} /></label>
			<label class="field"><span>Tax withheld</span><MoneyInput bind:value={form.tax} /></label>
			<label class="field"><span>Paid on</span><input class="input" type="date" bind:value={form.date} /></label>
		</div>
		{#if form.amount}
			<p class="notice">Net received: <b class="num">&nbsp;{money(form.amount - (form.tax ?? 0))}</b></p>
		{/if}
		<label class="field"><span>Note</span><input class="input" bind:value={form.note} placeholder="Optional" /></label>
	</form>
	{#snippet footer()}
		{#if form.id}<button class="btn danger" type="button" onclick={remove}>Delete</button><span style="flex:1"></span>{/if}
		<button class="btn" type="button" onclick={onclose}>Cancel</button>
		<button class="btn primary" form="dividend-form" disabled={busy || !form.amount || !brokers.length || !assets.length}>Save</button>
	{/snippet}
</Modal>

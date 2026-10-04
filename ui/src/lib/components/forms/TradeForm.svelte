<script lang="ts">
	import { untrack } from 'svelte';
	import { rpc } from '#lib/api.ts';
	import { confirmAction } from '#lib/confirm.svelte.ts';
	import { money, today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account, Asset, Trade } from '#lib/types.ts';
	import Modal from '../Modal.svelte';
	import MoneyInput from '../MoneyInput.svelte';

	interface Props {
		trade: Trade | null;
		accounts: Account[];
		assets: Asset[];
		onclose: () => void;
	}

	let { trade, accounts, assets, onclose }: Props = $props();
	let brokers = $derived(accounts.filter((a) => a.kind === 'brokerage' || a.id === trade?.account_id));

	let form = $state(
		untrack(() => ({
			id: trade?.id,
			account_id: trade?.account_id ?? accounts.find((a) => a.kind === 'brokerage')?.id,
			asset_id: trade?.asset_id ?? assets[0]?.id,
			date: trade?.date ?? today(),
			side: trade?.side ?? 'buy',
			quantity: trade ? String(trade.quantity) : '',
			price: trade ? String(trade.price) : '',
			fees: trade?.fees ?? 0,
			note: trade?.note ?? ''
		}))
	);
	let busy = $state(false);

	const num = (text: string) => Number(text.replace(',', '.'));
	let total = $derived.by(() => {
		const q = num(form.quantity);
		const p = num(form.price);
		if (!(q > 0) || !(p >= 0)) return null;
		const gross = Math.round(q * p * 100);
		return form.side === 'buy' ? gross + (form.fees ?? 0) : gross - (form.fees ?? 0);
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		try {
			await rpc('save_trade', { trade: { ...form, quantity: num(form.quantity), price: num(form.price), fees: form.fees ?? 0 } });
			toasts.show(form.id ? 'Trade updated' : 'Trade recorded');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!(await confirmAction({ title: 'Delete this trade?', message: 'Holdings and cash in the account are recalculated.', confirm: 'Delete', danger: true }))) return;
		try {
			await rpc('delete_trade', { id: form.id });
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		}
	}
</script>

<Modal title={form.id ? 'Edit trade' : 'Record a trade'} {onclose}>
	{#if !brokers.length || !assets.length}
		<p class="muted">
			You need {!brokers.length ? 'a brokerage account (Accounts page)' : ''}{!brokers.length && !assets.length ? ' and ' : ''}{!assets.length ? 'an asset (Assets tab)' : ''} first.
		</p>
	{:else}
		<form id="trade-form" class="grid" onsubmit={save}>
			<div class="tabs" role="group" aria-label="Side">
				<button type="button" class:active={form.side === 'buy'} onclick={() => (form.side = 'buy')}>Buy</button>
				<button type="button" class:active={form.side === 'sell'} onclick={() => (form.side = 'sell')}>Sell</button>
			</div>
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
				<label class="field"><span>Quantity</span><input class="input money" inputmode="decimal" bind:value={form.quantity} required /></label>
				<label class="field"><span>Price per unit</span><input class="input money" inputmode="decimal" bind:value={form.price} required /></label>
			</div>
			<div class="row">
				<label class="field"><span>Fees</span><MoneyInput bind:value={form.fees} /></label>
				<label class="field"><span>Date</span><input class="input" type="date" bind:value={form.date} /></label>
			</div>
			<label class="field"><span>Note</span><input class="input" bind:value={form.note} placeholder="Optional" /></label>
			{#if total !== null}
				<p class="notice">
					{form.side === 'buy' ? 'Takes' : 'Adds'} <b class="num">{money(total)}</b>&nbsp;{form.side === 'buy' ? 'from' : 'to'} the account's cash, fees included.
				</p>
			{/if}
		</form>
	{/if}
	{#snippet footer()}
		{#if form.id}<button class="btn danger" type="button" onclick={remove}>Delete</button><span style="flex:1"></span>{/if}
		<button class="btn" type="button" onclick={onclose}>Cancel</button>
		<button class="btn primary" form="trade-form" disabled={busy || total === null}>Save</button>
	{/snippet}
</Modal>

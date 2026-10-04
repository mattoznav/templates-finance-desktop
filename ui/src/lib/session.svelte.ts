import { onLocked, rpc } from './api.ts';
import type { Status } from './types.ts';

// Activity in the window keeps the vault open; the core decides when it locks.
// The window only reports activity (at most every 20 seconds) and polls the
// status, so the lock screen appears even while the user is away.
const PING_EVERY_MS = 20_000;
const POLL_EVERY_MS = 10_000;

class Session {
	status = $state<Status | null>(null);
	currency = $state('EUR');
	/** Bumped after every change, so pages know to reload their data. */
	version = $state(0);
	/** True when the vault locked itself, rather than the user locking it. */
	lockedByTimeout = $state(false);

	private lastPing = 0;
	private timer: ReturnType<typeof setInterval> | null = null;

	get unlocked(): boolean {
		return !!this.status?.unlocked;
	}

	async refresh(): Promise<Status> {
		const status = await rpc<Status>('status');
		this.apply(status);
		return status;
	}

	apply(status: Status, manual = false): void {
		if (this.status?.unlocked && !status.unlocked) this.lockedByTimeout = !manual;
		if (status.unlocked) this.lockedByTimeout = false;
		this.status = status;
		if (status.currency) this.currency = status.currency;
	}

	changed(): void {
		this.version += 1;
	}

	async lock(): Promise<void> {
		this.apply(await rpc<Status>('lock'), true);
	}

	start(): () => void {
		const stop = onLocked(() => {
			if (this.status?.unlocked) this.apply({ ...this.status, unlocked: false, demo: false });
		});
		const activity = () => {
			if (!this.unlocked) return;
			const now = Date.now();
			if (now - this.lastPing < PING_EVERY_MS) return;
			this.lastPing = now;
			rpc<Status>('ping').then((s) => this.apply(s)).catch(() => {});
		};
		const events = ['pointerdown', 'keydown', 'wheel', 'pointermove'] as const;
		events.forEach((e) => window.addEventListener(e, activity, { passive: true }));
		this.timer = setInterval(() => {
			if (this.unlocked) this.refresh().catch(() => {});
		}, POLL_EVERY_MS);
		return () => {
			stop();
			events.forEach((e) => window.removeEventListener(e, activity));
			if (this.timer) clearInterval(this.timer);
		};
	}
}

export const session = new Session();

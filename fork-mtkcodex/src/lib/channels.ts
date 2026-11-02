import { emailConfigured, receivingConfigured } from '@/lib/email';
import { pushConfigured, telegramConfigured } from '@/lib/notify';
import { storageMode } from '@/lib/leads';
import { whatsappConfigured } from '@/lib/whatsapp';

/** Which channels and alerts are switched on, for the inbox and Settings page. */
export type ChannelStatus = {
  database: boolean;
  chat: boolean;
  whatsapp: boolean;
  emailSend: boolean;
  emailReceive: boolean;
  push: boolean;
  telegram: boolean;
  booking: boolean;
};

export function channelStatus(): ChannelStatus {
  const database = storageMode() !== 'readonly';
  return {
    database,
    chat: database,
    whatsapp: whatsappConfigured(),
    emailSend: emailConfigured(),
    emailReceive: receivingConfigured(),
    push: pushConfigured(),
    telegram: telegramConfigured(),
    booking: Boolean((process.env.NEXT_PUBLIC_BOOKING_URL || '').trim()),
  };
}

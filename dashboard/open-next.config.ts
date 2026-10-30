import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// This operator dashboard has no ISR pages and needs no R2 cache uploader.
export default defineCloudflareConfig();

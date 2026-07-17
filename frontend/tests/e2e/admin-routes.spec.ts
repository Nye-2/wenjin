import { test, expect } from "@playwright/test";

test.describe("admin routes", () => {
  test.skip(
    !process.env.ADMIN_EMAIL || !process.env.ADMIN_PASSWORD,
    "requires ADMIN_EMAIL and ADMIN_PASSWORD",
  );

  test("sidebar navigates between admin pages", async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/login`);
    await page.fill('input[name="email"]', process.env.ADMIN_EMAIL!);
    await page.fill('input[name="password"]', process.env.ADMIN_PASSWORD!);
    await page.click('button[type="submit"]');
    await page.waitForURL(/dashboard/);

    await page.goto(`${baseURL}/dashboard/admin`);
    await expect(page.locator("h1")).toContainText("管理总览");

    await page.click('a[href="/dashboard/admin/users"]');
    await expect(page).toHaveURL(/admin\/users/);
    await expect(page.locator("h1")).toContainText("用户管理");

    await page.click('a[href="/dashboard/admin/credits"]');
    await expect(page).toHaveURL(/admin\/credits$/);

    await page.click('a[href="/dashboard/admin/release-gate"]');
    await expect(page).toHaveURL(/admin\/release-gate/);

    await page.click('a[href="/dashboard/admin/logs"]');
    await expect(page).toHaveURL(/admin\/logs/);
  });
});

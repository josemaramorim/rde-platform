"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

const PUBLIC = ["/", "/login", "/forgot-password", "/reset-password", "/atualizar", "/bloqueado"];

export default function SessionProvider({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();

    useEffect(() => {
        const isPublic = PUBLIC.some(p => pathname === p || pathname.startsWith(p + "/"));
        if (isPublic) return;

        const token = sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token");
        if (!token) {
            router.replace("/login");
        }
    }, [pathname]);

    return <>{children}</>;
}

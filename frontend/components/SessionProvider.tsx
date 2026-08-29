"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";

const PUBLIC = ["/", "/login", "/forgot-password", "/reset-password", "/atualizar", "/bloqueado"];
const ALLOWED_UNLIBERATED = ["/setup", "/termo-risco", "/perfil", "/carteira"];

export default function SessionProvider({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { estado, loading } = useEstado();

    useEffect(() => {
        const isPublic = PUBLIC.some(p => pathname === p || pathname.startsWith(p + "/"));
        if (isPublic) return;

        const token = sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token");
        if (!token) {
            router.replace("/login");
            return;
        }

        // Bloqueia acesso a páginas operacionais se a licença não estiver liberada pelo Admin
        if (!loading && token && !estado.liberado && !estado.is_admin) {
            const isAllowed = ALLOWED_UNLIBERATED.some(p => pathname === p || pathname.startsWith(p + "/"));
            if (!isAllowed) {
                router.replace("/setup");
            }
        }
    }, [pathname, loading, estado.liberado, estado.is_admin, router]);

    return <>{children}</>;
}

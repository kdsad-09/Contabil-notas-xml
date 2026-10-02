
                    st.markdown(
                        f"**#{m['id']} — "
                        f"{m['fornecedor']}**  \n"
                        f"📅 Doc: {m['data']} | "
                        f"Venc: {m['vencimento']} | "
                        f"NF/Doc: "
                        f"{m.get('nr_documento', '—')}"
                    )

                    st.caption(
                        f"🏗️ {m['obra']} | "
                        f"📂 {m['categoria']} | "
                        f"💳 {m['forma_pagamento']}"
                        + (
                            f" | CNO: {m['cno']}"
                            if m.get("cno")
                            else ""
                        )
                    )

                with mc2:

                    st.metric(
                        "Valor",
                        _fmt_brl(
                            m.get(
                                "valor",
                                0
                            )
                        ),
                    )

                    if codigo_m:

                        st.caption(
                            f"Cod. Contábil: "
                            f"**{codigo_m}**"
                        )

                with mc3:

                    if st.button(
                        "🗑️",
                        key=(
                            f"del_lanc_{i}"
                        ),
                        help=(
                            "Excluir este lançamento"
                        ),
                    ):

                        st.session_state[
                            "lancamentos_manuais"
                        ].pop(i)

                        st.rerun()

                if m.get(
                    "observacao"
                ):

                    st.caption(
                        f"📝 "
                        f"{m['observacao']}"
                    )

        st.divider()

        if lancamentos:

            df_lanc = pd.DataFrame(
                lancamentos
            )

            csv_lanc = (
                df_lanc
                .to_csv(
                    index=False
                )
                .encode(
                    "utf-8-sig"
                )
            )

            st.download_button(
                "⬇️ Exportar Lançamentos Manuais (CSV)",
                data=csv_lanc,
                file_name=(
                    "hikari_lancamentos_manuais.csv"
                ),
                mime="text/csv",
                use_container_width=True,
            )

        if st.button(
            "🗑️ Limpar Todos os Lançamentos",
            type="secondary",
        ):

            st.session_state[
                "lancamentos_manuais"
            ] = []

            st.rerun()


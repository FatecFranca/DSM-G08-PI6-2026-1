/*
  Warnings:

  - You are about to drop the column `cluster_id` on the `pregnancies` table. All the data in the column will be lost.
  - You are about to drop the column `cluster_name` on the `pregnancies` table. All the data in the column will be lost.

*/
-- AlterTable
ALTER TABLE "pregnancies" DROP COLUMN "cluster_id",
DROP COLUMN "cluster_name",
ADD COLUMN     "current_cluster_id" SMALLINT,
ADD COLUMN     "current_cluster_name" VARCHAR(60),
ADD COLUMN     "current_hex_color" VARCHAR(7),
ADD COLUMN     "current_risk_level" VARCHAR(20);

-- AlterTable
ALTER TABLE "questionnaires" ADD COLUMN     "hex_color" VARCHAR(7),
ADD COLUMN     "metrics" JSONB,
ADD COLUMN     "recommendations" JSONB,
ADD COLUMN     "risk_level" VARCHAR(20);
